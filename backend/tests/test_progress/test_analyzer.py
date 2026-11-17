from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.services.evaluation.schemas import (
    EvaluationResult,
    TestCaseResult as EvaluationTestCaseResult,
)
from app.services.progress import (
    ProgressAttempt,
    ProgressClassification,
    analyze_progress,
)


def _evaluation(
    score: str | None,
    *,
    status: str = "WRONG_ANSWER",
    case_statuses: tuple[str, ...] = ("WRONG_ANSWER",),
    compilation_error: str | None = None,
    runtime_error: str | None = None,
) -> EvaluationResult:
    return EvaluationResult(
        status=status,  # type: ignore[arg-type]
        passed_tests=sum(case_status == "PASSED" for case_status in case_statuses),
        total_tests=len(case_statuses),
        score=Decimal(score) if score is not None else None,
        execution_time_ms=None,
        compilation_error=compilation_error,
        runtime_error=runtime_error,
        test_case_results=[
            EvaluationTestCaseResult(
                test_case_id=index + 1,
                status=case_status,  # type: ignore[arg-type]
                error_message="case failed" if case_status == "RUNTIME_ERROR" else None,
            )
            for index, case_status in enumerate(case_statuses)
        ],
    )


def _attempt(
    evaluation: EvaluationResult,
    *,
    student_id: int = 1,
    problem_id: int = 10,
    submitted_at: datetime | None = None,
) -> ProgressAttempt:
    return ProgressAttempt(
        student_id=student_id,
        problem_id=problem_id,
        submitted_at=submitted_at or datetime(2026, 1, 1, tzinfo=timezone.utc),
        evaluation=evaluation,
    )


@pytest.mark.parametrize(
    ("previous_score", "current_score", "expected"),
    [
        ("40", "40.06", ProgressClassification.IMPROVING),
        ("40", "39.94", ProgressClassification.REGRESSING),
        ("40", "40.05", ProgressClassification.STAGNANT),
        ("40", "39.95", ProgressClassification.STAGNANT),
        ("40", "40", ProgressClassification.STAGNANT),
    ],
)
def test_classifies_score_differences(
    previous_score: str,
    current_score: str,
    expected: ProgressClassification,
) -> None:
    previous = _attempt(_evaluation(previous_score))
    current = _attempt(
        _evaluation(current_score),
        submitted_at=previous.submitted_at + timedelta(minutes=1),
    )

    result = analyze_progress(previous, current)

    assert result.classification is expected
    assert result.score_difference == Decimal(current_score) - Decimal(previous_score)


def test_missing_score_has_no_classification_but_reports_errors() -> None:
    previous = _attempt(_evaluation("50"))
    current = _attempt(
        _evaluation(None, status="COMPILATION_ERROR", compilation_error="cannot compile"),
        submitted_at=previous.submitted_at + timedelta(minutes=1),
    )

    result = analyze_progress(previous, current)

    assert result.classification is None
    assert result.previous_score == Decimal("50")
    assert result.current_score is None
    assert result.score_difference is None
    assert result.diagnostics.current_errors == ("cannot compile",)


def test_missing_previous_score_is_handled_safely() -> None:
    previous = _attempt(
        _evaluation(None, status="COMPILATION_ERROR", compilation_error="bad source")
    )
    current = _attempt(
        _evaluation("10"),
        submitted_at=previous.submitted_at + timedelta(minutes=1),
    )

    result = analyze_progress(previous, current)

    assert result.classification is None
    assert result.score_difference is None
    assert result.diagnostics.previous_errors == ("bad source",)


def test_test_case_status_changes_are_reported() -> None:
    previous = _attempt(_evaluation("50", case_statuses=("PASSED", "WRONG_ANSWER")))
    current = _attempt(
        _evaluation("100", case_statuses=("PASSED", "PASSED")),
        submitted_at=previous.submitted_at + timedelta(minutes=1),
    )

    result = analyze_progress(previous, current)

    assert [
        (change.test_case_id, change.previous_status, change.current_status)
        for change in result.diagnostics.test_case_changes
    ] == [
        (2, "WRONG_ANSWER", "PASSED")
    ]


def test_runtime_errors_are_reported_as_supporting_diagnostics() -> None:
    previous = _attempt(_evaluation("50"))
    current = _attempt(
        _evaluation(
            "0",
            status="RUNTIME_ERROR",
            case_statuses=("RUNTIME_ERROR",),
            runtime_error="process failed",
        ),
        submitted_at=previous.submitted_at + timedelta(minutes=1),
    )

    result = analyze_progress(previous, current)

    assert result.classification is ProgressClassification.REGRESSING
    assert result.diagnostics.current_errors == ("process failed", "case failed")


def test_first_submission_is_an_unclassified_baseline() -> None:
    result = analyze_progress(None, _attempt(_evaluation("75")))

    assert result.classification is None
    assert result.previous_score is None
    assert result.current_score == Decimal("75")
    assert result.score_difference is None


@pytest.mark.parametrize(
    ("previous_ids", "current_ids", "message"),
    [
        ((1, 10), (2, 10), "same student"),
        ((1, 10), (1, 11), "same problem"),
    ],
)
def test_rejects_comparisons_across_student_or_problem(
    previous_ids: tuple[int, int],
    current_ids: tuple[int, int],
    message: str,
) -> None:
    previous = _attempt(
        _evaluation("20"),
        student_id=previous_ids[0],
        problem_id=previous_ids[1],
    )
    current = _attempt(
        _evaluation("30"),
        student_id=current_ids[0],
        problem_id=current_ids[1],
        submitted_at=previous.submitted_at + timedelta(minutes=1),
    )

    with pytest.raises(ValueError, match=message):
        analyze_progress(previous, current)


@pytest.mark.parametrize(
    "offset",
    [timedelta(0), -timedelta(seconds=1)],
)
def test_rejects_non_chronological_attempts(offset: timedelta) -> None:
    previous = _attempt(_evaluation("20"))
    current = _attempt(_evaluation("30"), submitted_at=previous.submitted_at + offset)

    with pytest.raises(ValueError, match="previous attempt must precede"):
        analyze_progress(previous, current)


def test_rejects_uncomparable_timestamp_timezones() -> None:
    previous = _attempt(_evaluation("20"), submitted_at=datetime(2026, 1, 1))
    current = _attempt(
        _evaluation("30"),
        submitted_at=datetime(2026, 1, 2, tzinfo=timezone.utc),
    )

    with pytest.raises(ValueError, match="timestamps must be comparable"):
        analyze_progress(previous, current)
