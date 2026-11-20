from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from app.core.config import Settings
from app.services.evaluation.comparator import normalize_output, outputs_match
from app.services.evaluation.engine import EvaluationEngine
from app.services.evaluation.java_runner import JavaRunner, ProcessResult
from app.services.evaluation.schemas import TestCaseInput

JAVA_AVAILABLE = shutil.which("javac") is not None and shutil.which("java") is not None


def test_comparator_normalizes_line_endings_and_outer_whitespace() -> None:
    assert normalize_output(" \r\nalpha\r\nbeta\t ") == "alpha\nbeta"
    assert outputs_match(" \r\nanswer\r\n ", "\nanswer ")


def test_comparator_rejects_different_output_and_internal_whitespace() -> None:
    assert not outputs_match("answer", "other")
    assert not outputs_match("two  spaces", "two spaces")


def test_java_class_name_rejects_paths_and_command_fragments() -> None:
    runner = JavaRunner(Settings())
    with pytest.raises(ValueError):
        runner.validate_class_name("../Main")
    with pytest.raises(ValueError):
        runner.validate_class_name("Main;java")


def test_empty_test_cases_are_rejected() -> None:
    with pytest.raises(ValueError, match="At least one test case"):
        EvaluationEngine().evaluate("public class Main {}", [])


@pytest.mark.skipif(not JAVA_AVAILABLE, reason="Java JDK executables are unavailable")
def test_valid_program_runs_multiple_cases_in_isolated_processes() -> None:
    cases = [
        TestCaseInput(2, "", "1", False, 2),
        TestCaseInput(1, "", "1", False, 1),
    ]
    source = """
public class Main {
    private static int count = 0;
    public static void main(String[] args) {
        System.out.println(++count);
    }
}
"""
    result = EvaluationEngine().evaluate(source, cases)

    assert result.status == "ACCEPTED"
    assert result.passed_tests == result.total_tests == 2
    assert str(result.score) == "100.00"
    assert [case.test_case_id for case in result.test_case_results] == [1, 2]
    assert [case.actual_output for case in result.test_case_results] == ["1\n", "1\n"]


@pytest.mark.skipif(not JAVA_AVAILABLE, reason="Java JDK executables are unavailable")
def test_wrong_answer_and_fractional_score() -> None:
    result = EvaluationEngine().evaluate(
        "public class Main { public static void main(String[] a) { System.out.println(\"x\"); } }",
        [
            TestCaseInput(1, "", "x", False, 1),
            TestCaseInput(2, "", "y", False, 2),
        ],
    )

    assert result.status == "WRONG_ANSWER"
    assert result.passed_tests == 1
    assert result.score is not None and str(result.score) == "50.00"


@pytest.mark.skipif(not JAVA_AVAILABLE, reason="Java JDK executables are unavailable")
def test_compilation_error_marks_all_cases_not_run() -> None:
    result = EvaluationEngine().evaluate(
        "public class Main { this is invalid; }",
        [TestCaseInput(1, "", "", False, 1)],
    )

    assert result.status == "COMPILATION_ERROR"
    assert result.passed_tests == result.total_tests == 0
    assert result.score is None
    assert result.compilation_error
    assert result.test_case_results[0].status == "NOT_RUN"


@pytest.mark.skipif(not JAVA_AVAILABLE, reason="Java JDK executables are unavailable")
def test_missing_main_method_is_a_runtime_error() -> None:
    result = EvaluationEngine().evaluate(
        "public class Main { public void helper() {} }",
        [TestCaseInput(1, "", "", False, 1)],
    )

    assert result.status == "RUNTIME_ERROR"
    assert result.test_case_results[0].status == "RUNTIME_ERROR"
    assert result.runtime_error


@pytest.mark.skipif(not JAVA_AVAILABLE, reason="Java JDK executables are unavailable")
def test_runtime_error_stops_execution_and_marks_remaining_cases_not_run() -> None:
    result = EvaluationEngine().evaluate(
        """
public class Main {
    public static void main(String[] args) {
        throw new RuntimeException("failure");
    }
}
""",
        [
            TestCaseInput(1, "", "", False, 1),
            TestCaseInput(2, "", "", False, 2),
        ],
    )

    assert result.status == "RUNTIME_ERROR"
    assert result.test_case_results[0].status == "RUNTIME_ERROR"
    assert result.test_case_results[1].status == "NOT_RUN"
    assert "failure" in (result.runtime_error or "")


@pytest.mark.skipif(not JAVA_AVAILABLE, reason="Java JDK executables are unavailable")
def test_timeout_stops_execution_and_marks_remaining_cases_not_run() -> None:
    config = Settings(JAVA_EXECUTION_TIMEOUT_SECONDS=0.2)
    result = EvaluationEngine(config=config).evaluate(
        """
public class Main {
    public static void main(String[] args) {
        while (true) {}
    }
}
""",
        [
            TestCaseInput(1, "", "", False, 1),
            TestCaseInput(2, "", "", False, 2),
        ],
    )

    assert result.status == "TIME_LIMIT_EXCEEDED"
    assert result.test_case_results[0].status == "TIME_LIMIT_EXCEEDED"
    assert result.test_case_results[1].status == "NOT_RUN"


@pytest.mark.skipif(not JAVA_AVAILABLE, reason="Java JDK executables are unavailable")
def test_input_output_comparison_and_empty_input() -> None:
    result = EvaluationEngine().evaluate(
        """
import java.util.Scanner;
public class Main {
    public static void main(String[] args) {
        Scanner scanner = new Scanner(System.in);
        System.out.println(scanner.hasNext() ? scanner.next() : "empty");
    }
}
""",
        [TestCaseInput(1, "", "empty", False, 1)],
    )
    assert result.status == "ACCEPTED"


@pytest.mark.skipif(not JAVA_AVAILABLE, reason="Java JDK executables are unavailable")
def test_non_default_class_name_can_be_configured() -> None:
    config = Settings(JAVA_CLASS_NAME="Solution")
    result = EvaluationEngine(config=config).evaluate(
        'public class Solution { public static void main(String[] a) { System.out.println("ok"); } }',
        [TestCaseInput(1, "", "ok", False, 1)],
    )
    assert result.status == "ACCEPTED"


def test_infrastructure_exception_is_not_misclassified(monkeypatch: pytest.MonkeyPatch) -> None:
    working_directories: list[Path] = []

    def fail_to_start(*args: object, **kwargs: object) -> None:
        working_directories.append(Path(str(kwargs["cwd"])))
        raise OSError("compiler unavailable")

    monkeypatch.setattr(
        "app.services.evaluation.java_runner.subprocess.run",
        fail_to_start,
    )
    result = EvaluationEngine().evaluate(
        "public class Main {}",
        [TestCaseInput(1, "", "", False, 1)],
    )

    assert result.status == "INTERNAL_ERROR"
    assert result.internal_error == "Evaluation infrastructure error: OSError."
    assert result.compilation_error is None
    assert result.score is None
    assert result.test_case_results[0].status == "NOT_RUN"
    assert len(working_directories) == 1
    assert not working_directories[0].exists()


def test_execution_infrastructure_failure_after_pass_keeps_results_without_score(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = JavaRunner(Settings())
    monkeypatch.setattr(
        runner,
        "compile",
        lambda source_code, work_dir, class_name: ProcessResult(0, "", "", 0),
    )
    executions = 0

    def fail_second_execution(
        work_dir: Path,
        class_name: str,
        input_data: str,
        timeout: float,
    ) -> ProcessResult:
        nonlocal executions
        executions += 1
        if executions == 2:
            raise OSError("runtime unavailable")
        return ProcessResult(0, "ok\n", "", 10)

    monkeypatch.setattr(runner, "execute", fail_second_execution)
    result = EvaluationEngine(runner=runner).evaluate(
        "public class Main {}",
        [
            TestCaseInput(1, "", "ok", False, 1),
            TestCaseInput(2, "", "ok", False, 2),
        ],
    )

    assert result.status == "INTERNAL_ERROR"
    assert result.score is None
    assert result.passed_tests == 1
    assert result.total_tests == 2
    assert result.internal_error == "Evaluation infrastructure error: OSError."
    assert [case.status for case in result.test_case_results] == [
        "PASSED",
        "NOT_RUN",
    ]
    assert result.test_case_results[0].actual_output == "ok\n"


def test_compilation_timeout_is_reported_as_time_limit_exceeded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def time_out(*args: object, **kwargs: object) -> None:
        import subprocess

        raise subprocess.TimeoutExpired(cmd="javac", timeout=1)

    monkeypatch.setattr(
        "app.services.evaluation.java_runner.subprocess.run",
        time_out,
    )
    result = EvaluationEngine().evaluate(
        "public class Main {}",
        [TestCaseInput(1, "", "", False, 1)],
    )

    assert result.status == "TIME_LIMIT_EXCEEDED"
    assert result.compilation_error == "Compilation exceeded its configured timeout."
    assert result.total_tests == 0
    assert result.test_case_results[0].status == "NOT_RUN"
