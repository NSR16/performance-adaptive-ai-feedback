from __future__ import annotations

import tempfile
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Sequence

from app.core.config import Settings, settings
from app.services.evaluation.comparator import outputs_match
from app.services.evaluation.java_runner import JavaRunner
from app.services.evaluation.schemas import (
    EvaluationResult,
    EvaluationStatus,
    TestCaseInput,
    TestCaseResult,
)


class EvaluationEngine:
    def __init__(
        self,
        runner: JavaRunner | None = None,
        config: Settings | None = None,
    ) -> None:
        self.config = config or settings
        self.runner = runner or JavaRunner(self.config)

    def evaluate(
        self,
        source_code: str,
        test_cases: Sequence[TestCaseInput],
        class_name: str | None = None,
    ) -> EvaluationResult:
        if not test_cases:
            raise ValueError("At least one test case is required.")

        selected_class_name = (
            class_name if class_name is not None else self.config.JAVA_CLASS_NAME
        )
        self.runner.validate_class_name(selected_class_name)
        ordered_cases = sorted(test_cases, key=lambda case: case.sequence_order)
        results: list[TestCaseResult] = []
        execution_time_ns = 0

        try:
            temporary_directory = tempfile.TemporaryDirectory(
                prefix="aiml-evaluation-"
            )
        except Exception as exc:
            return _internal_failure(
                ordered_cases,
                f"Evaluation infrastructure error: {type(exc).__name__}.",
            )

        with temporary_directory as directory:
            work_dir = Path(directory)
            try:
                compilation = self.runner.compile(
                    source_code,
                    work_dir,
                    selected_class_name,
                )
            except Exception as exc:
                return _internal_failure(
                    ordered_cases,
                    f"Evaluation infrastructure error: {type(exc).__name__}.",
                )

            if compilation.timed_out:
                return _result(
                    status="TIME_LIMIT_EXCEEDED",
                    passed_tests=0,
                    total_tests=0,
                    score=None,
                    execution_time_ms=0,
                    compilation_error="Compilation exceeded its configured timeout.",
                    runtime_error=None,
                    test_case_results=_not_run_results(ordered_cases),
                )
            if compilation.returncode != 0:
                diagnostic = compilation.stderr or compilation.stdout or "Java compilation failed."
                return _result(
                    status="COMPILATION_ERROR",
                    passed_tests=0,
                    total_tests=0,
                    score=None,
                    execution_time_ms=0,
                    compilation_error=diagnostic,
                    runtime_error=None,
                    test_case_results=_not_run_results(ordered_cases),
                )

            passed_tests = 0
            failure_status: EvaluationStatus | None = None
            runtime_error: str | None = None
            for case_index, case in enumerate(ordered_cases):
                try:
                    execution = self.runner.execute(
                        work_dir,
                        selected_class_name,
                        case.input_data,
                        self.config.JAVA_EXECUTION_TIMEOUT_SECONDS,
                    )
                except Exception as exc:
                    return _internal_failure(
                        ordered_cases,
                        f"Evaluation infrastructure error: {type(exc).__name__}.",
                        results=results,
                        execution_time_ms=execution_time_ns // 1_000_000,
                    )

                execution_time_ns += execution.elapsed_ns
                if execution.timed_out:
                    failure_status = "TIME_LIMIT_EXCEEDED"
                    results.append(
                        TestCaseResult(
                            test_case_id=case.test_case_id,
                            status="TIME_LIMIT_EXCEEDED",
                            actual_output=execution.stdout,
                            execution_time_ms=execution.elapsed_ms,
                            error_message="Execution exceeded its configured timeout.",
                        )
                    )
                    results.extend(_not_run_results(ordered_cases[case_index + 1 :]))
                    break
                if execution.returncode != 0:
                    failure_status = "RUNTIME_ERROR"
                    runtime_error = execution.stderr or f"Java process exited with code {execution.returncode}."
                    results.append(
                        TestCaseResult(
                            test_case_id=case.test_case_id,
                            status="RUNTIME_ERROR",
                            actual_output=execution.stdout,
                            execution_time_ms=execution.elapsed_ms,
                            error_message=runtime_error,
                        )
                    )
                    results.extend(_not_run_results(ordered_cases[case_index + 1 :]))
                    break

                if outputs_match(execution.stdout, case.expected_output):
                    passed_tests += 1
                    case_status = "PASSED"
                    error_message = None
                else:
                    failure_status = failure_status or "WRONG_ANSWER"
                    case_status = "WRONG_ANSWER"
                    error_message = None
                results.append(
                    TestCaseResult(
                        test_case_id=case.test_case_id,
                        status=case_status,
                        actual_output=execution.stdout,
                        execution_time_ms=execution.elapsed_ms,
                        error_message=error_message,
                    )
                )

        total_tests = len(ordered_cases)
        status = failure_status or "ACCEPTED"
        score = _score(passed_tests, total_tests)
        return _result(
            status=status,
            passed_tests=passed_tests,
            total_tests=total_tests,
            score=score,
            execution_time_ms=execution_time_ns // 1_000_000,
            compilation_error=None,
            runtime_error=runtime_error,
            test_case_results=results,
        )


def _score(passed_tests: int, total_tests: int) -> Decimal:
    return (Decimal(passed_tests) * Decimal("100") / Decimal(total_tests)).quantize(
        Decimal("0.01"),
        rounding=ROUND_HALF_UP,
    )


def _not_run_results(cases: Sequence[TestCaseInput]) -> list[TestCaseResult]:
    return [
        TestCaseResult(test_case_id=case.test_case_id, status="NOT_RUN")
        for case in cases
    ]


def _internal_failure(
    cases: Sequence[TestCaseInput],
    message: str,
    results: list[TestCaseResult] | None = None,
    execution_time_ms: int = 0,
) -> EvaluationResult:
    completed = list(results or [])
    completed.extend(_not_run_results(cases[len(completed) :]))
    return _result(
        status="INTERNAL_ERROR",
        passed_tests=sum(result.status == "PASSED" for result in completed),
        total_tests=len(cases),
        score=_score(sum(result.status == "PASSED" for result in completed), len(cases)),
        execution_time_ms=execution_time_ms,
        compilation_error=None,
        runtime_error=None,
        test_case_results=completed,
        internal_error=message,
    )


def _result(
    status: EvaluationStatus,
    passed_tests: int,
    total_tests: int,
    score: Decimal | None,
    execution_time_ms: int | None,
    compilation_error: str | None,
    runtime_error: str | None,
    test_case_results: list[TestCaseResult],
    internal_error: str | None = None,
) -> EvaluationResult:
    return EvaluationResult(
        status=status,
        passed_tests=passed_tests,
        total_tests=total_tests,
        score=score,
        execution_time_ms=execution_time_ms,
        compilation_error=compilation_error,
        runtime_error=runtime_error,
        test_case_results=test_case_results,
        internal_error=internal_error,
    )
