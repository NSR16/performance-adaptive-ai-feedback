from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum

from app.services.evaluation.schemas import EvaluationResult

SCORE_DIFFERENCE_THRESHOLD = Decimal("0.05")


class ProgressClassification(str, Enum):
    IMPROVING = "IMPROVING"
    STAGNANT = "STAGNANT"
    REGRESSING = "REGRESSING"


@dataclass(frozen=True)
class ProgressAttempt:
    student_id: int
    problem_id: int
    submitted_at: datetime
    evaluation: EvaluationResult


@dataclass(frozen=True)
class TestCaseChange:
    test_case_id: int
    previous_status: str | None
    current_status: str | None


@dataclass(frozen=True)
class ProgressDiagnostics:
    test_case_changes: tuple[TestCaseChange, ...]
    previous_errors: tuple[str, ...]
    current_errors: tuple[str, ...]


@dataclass(frozen=True)
class ProgressAnalysis:
    classification: ProgressClassification | None
    previous_score: Decimal | None
    current_score: Decimal | None
    score_difference: Decimal | None
    diagnostics: ProgressDiagnostics


def analyze_progress(
    previous: ProgressAttempt | None,
    current: ProgressAttempt,
) -> ProgressAnalysis:
    """Compare consecutive attempts; a missing previous attempt is a baseline."""
    if previous is not None:
        if previous.student_id != current.student_id:
            raise ValueError("Attempts must belong to the same student.")
        if previous.problem_id != current.problem_id:
            raise ValueError("Attempts must belong to the same problem.")
        try:
            is_chronological = previous.submitted_at < current.submitted_at
        except TypeError as exc:
            raise ValueError("Attempt timestamps must be comparable.") from exc
        if not is_chronological:
            raise ValueError("The previous attempt must precede the current attempt.")

    previous_evaluation = previous.evaluation if previous is not None else None
    changes = _test_case_changes(
        previous_evaluation,
        current.evaluation,
    )
    diagnostics = ProgressDiagnostics(
        test_case_changes=changes,
        previous_errors=_errors(previous_evaluation),
        current_errors=_errors(current.evaluation),
    )
    previous_score = previous_evaluation.score if previous_evaluation else None
    current_score = current.evaluation.score
    if previous is None or previous_score is None or current_score is None:
        return ProgressAnalysis(
            classification=None,
            previous_score=previous_score,
            current_score=current_score,
            score_difference=None,
            diagnostics=diagnostics,
        )

    difference = current_score - previous_score
    if difference > SCORE_DIFFERENCE_THRESHOLD:
        classification = ProgressClassification.IMPROVING
    elif difference < -SCORE_DIFFERENCE_THRESHOLD:
        classification = ProgressClassification.REGRESSING
    else:
        classification = ProgressClassification.STAGNANT

    return ProgressAnalysis(
        classification=classification,
        previous_score=previous_score,
        current_score=current_score,
        score_difference=difference,
        diagnostics=diagnostics,
    )


def _test_case_changes(
    previous: EvaluationResult | None,
    current: EvaluationResult,
) -> tuple[TestCaseChange, ...]:
    previous_results = (
        {result.test_case_id: result.status for result in previous.test_case_results}
        if previous is not None
        else {}
    )
    current_results = {
        result.test_case_id: result.status for result in current.test_case_results
    }
    return tuple(
        TestCaseChange(
            test_case_id=test_case_id,
            previous_status=previous_results.get(test_case_id),
            current_status=current_results.get(test_case_id),
        )
        for test_case_id in sorted(previous_results.keys() | current_results.keys())
        if previous_results.get(test_case_id) != current_results.get(test_case_id)
    )


def _errors(evaluation: EvaluationResult | None) -> tuple[str, ...]:
    if evaluation is None:
        return ()
    errors = [
        error
        for error in (
            evaluation.compilation_error,
            evaluation.runtime_error,
            evaluation.internal_error,
        )
        if error
    ]
    errors.extend(
        result.error_message
        for result in evaluation.test_case_results
        if result.error_message
    )
    return tuple(dict.fromkeys(errors))
