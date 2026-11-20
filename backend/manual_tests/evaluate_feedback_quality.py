from __future__ import annotations

import argparse
import asyncio
import json
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

from app.core.config import settings
from app.services.adaptive import AssistanceLevel
from app.services.evaluation.schemas import EvaluationResult, TestCaseResult
from app.services.feedback import OllamaFeedbackGenerator, build_feedback_prompt


@dataclass(frozen=True)
class ScenarioTestCase:
    test_case_id: int
    input_data: str
    expected_output: str


@dataclass(frozen=True)
class FeedbackScenario:
    scenario_id: str
    name: str
    problem_description: str
    source_code: str
    test_cases: tuple[ScenarioTestCase, ...]
    evaluation_result: EvaluationResult
    assistance_levels: tuple[AssistanceLevel, ...]
    expected_observations: tuple[str, ...]


ALL_ASSISTANCE_LEVELS = (
    AssistanceLevel.LOW,
    AssistanceLevel.MODERATE,
    AssistanceLevel.HIGH,
)

SCENARIOS = (
    FeedbackScenario(
        scenario_id="scenario_1",
        name="Multi-requirement wrong answer",
        problem_description=(
            "Read two integers and print their sum and product, in that order."
        ),
        source_code="""import java.util.Scanner;

public class Main {
    public static void main(String[] args) {
        Scanner scanner = new Scanner(System.in);
        int first = scanner.nextInt();
        int second = scanner.nextInt();
        int sum = first + second;
        int difference = first - second;
        System.out.println(sum + " " + difference);
    }
}""",
        test_cases=(
            ScenarioTestCase(1, "2 3\n", "5 6\n"),
            ScenarioTestCase(2, "4 2\n", "6 8\n"),
        ),
        evaluation_result=EvaluationResult(
            status="WRONG_ANSWER",
            passed_tests=0,
            total_tests=2,
            score=Decimal("0.00"),
            execution_time_ms=None,
            compilation_error=None,
            runtime_error=None,
            test_case_results=[
                TestCaseResult(
                    test_case_id=1,
                    status="WRONG_ANSWER",
                    actual_output="5 -1\n",
                ),
                TestCaseResult(
                    test_case_id=2,
                    status="WRONG_ANSWER",
                    actual_output="6 2\n",
                ),
            ],
        ),
        assistance_levels=ALL_ASSISTANCE_LEVELS,
        expected_observations=(
            "LOW: conceptual hint without direct correction.",
            "MODERATE: identify the incorrect operation and guide the student.",
            "HIGH: provide a correct implementation that preserves both outputs.",
        ),
    ),
    FeedbackScenario(
        scenario_id="scenario_2",
        name="Compilation error",
        problem_description="Read two integers from standard input and print their sum.",
        source_code="""import java.util.Scanner;

public class Main {
    public static void main(String[] args) {
        Scanner scanner = new Scanner(System.in);
        int first = scanner.nextInt();
        int second = scanner.nextInt();
        System.out.println(first + secondValue);
    }
}""",
        test_cases=(ScenarioTestCase(1, "2 3\n", "5\n"),),
        evaluation_result=EvaluationResult(
            status="COMPILATION_ERROR",
            passed_tests=0,
            total_tests=0,
            score=None,
            execution_time_ms=0,
            compilation_error="cannot find symbol: variable secondValue",
            runtime_error=None,
            test_case_results=[TestCaseResult(test_case_id=1, status="NOT_RUN")],
        ),
        assistance_levels=ALL_ASSISTANCE_LEVELS,
        expected_observations=(
            "LOW: hint about using the declared input variable.",
            "MODERATE: explain the undefined-variable issue without replacement code.",
            "HIGH: correct the compilation error and preserve the complete sum task.",
        ),
    ),
    FeedbackScenario(
        scenario_id="scenario_3",
        name="Runtime error",
        problem_description=(
            "Read an integer and print its reciprocal. If the input is zero, "
            "print 'undefined'."
        ),
        source_code="""import java.util.Scanner;

public class Main {
    public static void main(String[] args) {
        Scanner scanner = new Scanner(System.in);
        int value = scanner.nextInt();
        int reciprocal = 1 / value;
        System.out.println(reciprocal);
    }
}""",
        test_cases=(ScenarioTestCase(1, "0\n", "undefined\n"),),
        evaluation_result=EvaluationResult(
            status="RUNTIME_ERROR",
            passed_tests=0,
            total_tests=1,
            score=Decimal("0.00"),
            execution_time_ms=1,
            compilation_error=None,
            runtime_error="java.lang.ArithmeticException: / by zero",
            test_case_results=[
                TestCaseResult(
                    test_case_id=1,
                    status="RUNTIME_ERROR",
                    actual_output="",
                    execution_time_ms=1,
                    error_message="java.lang.ArithmeticException: / by zero",
                )
            ],
        ),
        assistance_levels=ALL_ASSISTANCE_LEVELS,
        expected_observations=(
            "LOW: conceptual guidance about the operation.",
            "MODERATE: explain the runtime issue and suggest handling the zero case.",
            "HIGH: provide a suitable correction without changing the stated requirements.",
        ),
    ),
    FeedbackScenario(
        scenario_id="scenario_4",
        name="Internal infrastructure error",
        problem_description="Read two integers from standard input and print their sum.",
        source_code="""import java.util.Scanner;

public class Main {
    public static void main(String[] args) {
        Scanner scanner = new Scanner(System.in);
        int first = scanner.nextInt();
        int second = scanner.nextInt();
        System.out.println(first + second);
    }
}""",
        test_cases=(
            ScenarioTestCase(1, "2 3\n", "5\n"),
            ScenarioTestCase(2, "4 6\n", "10\n"),
        ),
        evaluation_result=EvaluationResult(
            status="INTERNAL_ERROR",
            passed_tests=1,
            total_tests=2,
            score=None,
            execution_time_ms=1,
            compilation_error=None,
            runtime_error=None,
            test_case_results=[
                TestCaseResult(
                    test_case_id=1,
                    status="PASSED",
                    actual_output="5\n",
                    execution_time_ms=1,
                ),
                TestCaseResult(test_case_id=2, status="NOT_RUN"),
            ],
            internal_error="Simulated evaluator infrastructure failure.",
        ),
        assistance_levels=(AssistanceLevel.HIGH,),
        expected_observations=(
            "Do not blame the student's code or invent a programming defect.",
            "Explain that evaluation could not be completed.",
        ),
    ),
    FeedbackScenario(
        scenario_id="scenario_5",
        name="Accepted submission",
        problem_description="Read two integers from standard input and print their sum.",
        source_code="""import java.util.Scanner;

public class Main {
    public static void main(String[] args) {
        Scanner scanner = new Scanner(System.in);
        int first = scanner.nextInt();
        int second = scanner.nextInt();
        System.out.println(first + second);
    }
}""",
        test_cases=(
            ScenarioTestCase(1, "2 3\n", "5\n"),
            ScenarioTestCase(2, "4 6\n", "10\n"),
        ),
        evaluation_result=EvaluationResult(
            status="ACCEPTED",
            passed_tests=2,
            total_tests=2,
            score=Decimal("100.00"),
            execution_time_ms=2,
            compilation_error=None,
            runtime_error=None,
            test_case_results=[
                TestCaseResult(
                    test_case_id=1,
                    status="PASSED",
                    actual_output="5\n",
                    execution_time_ms=1,
                ),
                TestCaseResult(
                    test_case_id=2,
                    status="PASSED",
                    actual_output="10\n",
                    execution_time_ms=1,
                ),
            ],
        ),
        assistance_levels=(AssistanceLevel.HIGH,),
        expected_observations=(
            "Acknowledge successful evaluation.",
            "Do not invent bugs, claim the program is incorrect, or prescribe a correction.",
        ),
    ),
)


def _validate_scenarios() -> int:
    expected_results = {
        "scenario_1": ("WRONG_ANSWER", Decimal("0.00")),
        "scenario_2": ("COMPILATION_ERROR", None),
        "scenario_3": ("RUNTIME_ERROR", Decimal("0.00")),
        "scenario_4": ("INTERNAL_ERROR", None),
        "scenario_5": ("ACCEPTED", Decimal("100.00")),
    }
    generation_count = 0
    if len(SCENARIOS) != len(expected_results):
        raise ValueError("The evaluation suite must contain exactly five scenarios.")

    for scenario in SCENARIOS:
        expected_status, expected_score = expected_results[scenario.scenario_id]
        result = scenario.evaluation_result
        if (result.status, result.score) != (expected_status, expected_score):
            raise ValueError(
                f"{scenario.scenario_id} has an unexpected evaluation status or score."
            )
        if result.passed_tests > result.total_tests:
            raise ValueError(f"{scenario.scenario_id} has inconsistent test counts.")
        if not scenario.problem_description or not scenario.source_code:
            raise ValueError(f"{scenario.scenario_id} is missing prompt input.")
        if not scenario.assistance_levels:
            raise ValueError(f"{scenario.scenario_id} has no assistance levels.")

        for level in scenario.assistance_levels:
            build_feedback_prompt(
                scenario.problem_description,
                scenario.source_code,
                result,
                level,
            )
            generation_count += 1

    if generation_count != 11:
        raise ValueError(f"Expected 11 generations; found {generation_count}.")
    return generation_count


def _evaluation_metadata(result: EvaluationResult) -> dict[str, Any]:
    return {
        "status": result.status,
        "passed_tests": result.passed_tests,
        "total_tests": result.total_tests,
        "score": str(result.score) if result.score is not None else None,
        "execution_time_ms": result.execution_time_ms,
        "compilation_error": result.compilation_error,
        "runtime_error": result.runtime_error,
        "internal_error": result.internal_error,
        "test_case_results": [asdict(test_result) for test_result in result.test_case_results],
    }


def _scenario_metadata(scenario: FeedbackScenario) -> dict[str, Any]:
    return {
        "scenario_id": scenario.scenario_id,
        "name": scenario.name,
        "problem_description": scenario.problem_description,
        "source_code": scenario.source_code,
        "test_cases": [asdict(test_case) for test_case in scenario.test_cases],
        "evaluation": _evaluation_metadata(scenario.evaluation_result),
        "expected_observations": list(scenario.expected_observations),
    }


def _save_results(
    output_path: Path,
    run_metadata: dict[str, Any],
    records: list[dict[str, Any]],
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    document = {
        "run": run_metadata,
        "results": records,
    }
    temporary_path = output_path.with_suffix(f"{output_path.suffix}.tmp")
    temporary_path.write_text(
        json.dumps(document, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    temporary_path.replace(output_path)


async def _run_evaluation(output_path: Path, expected_count: int) -> None:
    generator = OllamaFeedbackGenerator(config=settings)
    run_metadata: dict[str, Any] = {
        "started_at": datetime.now(timezone.utc).isoformat(),
        "status": "IN_PROGRESS",
        "expected_generation_count": expected_count,
        "configured_model": settings.OLLAMA_MODEL,
        "ollama_base_url": settings.OLLAMA_BASE_URL,
        "ollama_timeout_seconds": settings.OLLAMA_TIMEOUT,
        "generation_request": "Production generator defaults; stream=False.",
    }
    records: list[dict[str, Any]] = []
    _save_results(output_path, run_metadata, records)

    for scenario in SCENARIOS:
        for level in scenario.assistance_levels:
            started = time.monotonic()
            generated_at = datetime.now(timezone.utc).isoformat()
            try:
                generation = await generator.generate_feedback(
                    problem_description=scenario.problem_description,
                    source_code=scenario.source_code,
                    evaluation_result=scenario.evaluation_result,
                    assistance_level=level,
                )
                record = {
                    "scenario_id": scenario.scenario_id,
                    "scenario_name": scenario.name,
                    "assistance_level": level.value,
                    "timestamp": generated_at,
                    "duration_seconds": round(time.monotonic() - started, 3),
                    "model_name": generation.model_name,
                    "generation_status": generation.generation_status,
                    "feedback_text": generation.feedback_text,
                    "error_message": generation.error_message,
                    "input": _scenario_metadata(scenario),
                }
            except Exception as exc:
                record = {
                    "scenario_id": scenario.scenario_id,
                    "scenario_name": scenario.name,
                    "assistance_level": level.value,
                    "timestamp": generated_at,
                    "duration_seconds": round(time.monotonic() - started, 3),
                    "model_name": settings.OLLAMA_MODEL,
                    "generation_status": "FAILED",
                    "feedback_text": None,
                    "error_message": (
                        f"Unexpected generation failure: {type(exc).__name__}: {exc}"
                    ),
                    "input": _scenario_metadata(scenario),
                }

            records.append(record)
            run_metadata["completed_generation_count"] = len(records)
            _save_results(output_path, run_metadata, records)
            print(
                f"[{len(records)}/{expected_count}] {scenario.scenario_id} "
                f"{level.value}: {record['generation_status']}"
            )

    failed_count = sum(
        record["generation_status"] != "SUCCEEDED" for record in records
    )
    run_metadata["completed_at"] = datetime.now(timezone.utc).isoformat()
    run_metadata["status"] = "COMPLETED_WITH_FAILURES" if failed_count else "COMPLETED"
    run_metadata["failed_generation_count"] = failed_count
    _save_results(output_path, run_metadata, records)
    print(f"Results saved to: {output_path.resolve()}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate actual Ollama feedback for the fixed M9 manual suite."
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Output JSON path (defaults to a timestamped file in manual_tests/outputs).",
    )
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Validate the fixed scenarios and production prompts without calling Ollama.",
    )
    args = parser.parse_args()

    generation_count = _validate_scenarios()
    if args.validate_only:
        print(
            f"Validated {len(SCENARIOS)} scenarios and "
            f"{generation_count} production prompts."
        )
        return

    output_path = args.output
    if output_path is None:
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        output_path = (
            Path(__file__).resolve().parent
            / "outputs"
            / f"feedback_evaluation_{timestamp}.json"
        )
    asyncio.run(_run_evaluation(output_path, generation_count))


if __name__ == "__main__":
    main()
