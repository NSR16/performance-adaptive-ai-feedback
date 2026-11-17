import pytest

from app.services.adaptive import (
    INITIAL_ASSISTANCE_LEVEL,
    AssistanceLevel,
    select_assistance,
)
from app.services.progress import ProgressClassification


@pytest.mark.parametrize(
    ("state", "classification", "expected"),
    [
        (AssistanceLevel.HIGH, ProgressClassification.IMPROVING, AssistanceLevel.MODERATE),
        (AssistanceLevel.HIGH, ProgressClassification.STAGNANT, AssistanceLevel.HIGH),
        (AssistanceLevel.HIGH, ProgressClassification.REGRESSING, AssistanceLevel.HIGH),
        (AssistanceLevel.MODERATE, ProgressClassification.IMPROVING, AssistanceLevel.LOW),
        (AssistanceLevel.MODERATE, ProgressClassification.STAGNANT, AssistanceLevel.MODERATE),
        (AssistanceLevel.MODERATE, ProgressClassification.REGRESSING, AssistanceLevel.HIGH),
        (AssistanceLevel.LOW, ProgressClassification.IMPROVING, AssistanceLevel.LOW),
        (AssistanceLevel.LOW, ProgressClassification.STAGNANT, AssistanceLevel.LOW),
        (AssistanceLevel.LOW, ProgressClassification.REGRESSING, AssistanceLevel.HIGH),
    ],
)
def test_transition_table(
    state: AssistanceLevel,
    classification: ProgressClassification,
    expected: AssistanceLevel,
) -> None:
    # Improvements use a prior streak so this case tests the table after hysteresis.
    result = select_assistance(
        classification,
        previous_assistance=state,
        previous_improvement_streak=1 if classification is ProgressClassification.IMPROVING else 0,
    )

    assert result.selected_assistance is expected


def test_one_improvement_does_not_reduce_assistance() -> None:
    result = select_assistance(ProgressClassification.IMPROVING)

    assert result.previous_assistance is AssistanceLevel.MODERATE
    assert result.selected_assistance is AssistanceLevel.MODERATE
    assert result.previous_improvement_streak == 0
    assert result.updated_improvement_streak == 1
    assert not result.assistance_changed


def test_two_consecutive_improvements_reduce_assistance() -> None:
    first = select_assistance(ProgressClassification.IMPROVING)
    second = select_assistance(
        ProgressClassification.IMPROVING,
        previous_assistance=first.selected_assistance,
        previous_improvement_streak=first.updated_improvement_streak,
    )

    assert second.selected_assistance is AssistanceLevel.LOW
    assert second.previous_improvement_streak == 1
    assert second.updated_improvement_streak == 2
    assert second.assistance_changed


def test_stagnation_resets_improvement_streak() -> None:
    result = select_assistance(
        ProgressClassification.STAGNANT,
        previous_assistance=AssistanceLevel.MODERATE,
        previous_improvement_streak=1,
    )

    assert result.selected_assistance is AssistanceLevel.MODERATE
    assert result.updated_improvement_streak == 0


def test_regression_resets_streak_and_increases_assistance_immediately() -> None:
    result = select_assistance(
        ProgressClassification.REGRESSING,
        previous_assistance=AssistanceLevel.LOW,
        previous_improvement_streak=1,
    )

    assert result.selected_assistance is AssistanceLevel.HIGH
    assert result.updated_improvement_streak == 0
    assert result.assistance_changed


def test_low_improving_remains_low() -> None:
    result = select_assistance(
        ProgressClassification.IMPROVING,
        previous_assistance=AssistanceLevel.LOW,
        previous_improvement_streak=1,
    )

    assert result.selected_assistance is AssistanceLevel.LOW
    assert result.updated_improvement_streak == 2
    assert not result.assistance_changed


def test_initial_state_is_moderate() -> None:
    assert INITIAL_ASSISTANCE_LEVEL is AssistanceLevel.MODERATE
    assert select_assistance(ProgressClassification.STAGNANT).previous_assistance is AssistanceLevel.MODERATE


def test_baseline_without_classification_retains_initial_state_and_zero_streak() -> None:
    result = select_assistance(None)

    assert result.previous_assistance is AssistanceLevel.MODERATE
    assert result.selected_assistance is AssistanceLevel.MODERATE
    assert result.progress_classification is None
    assert result.previous_improvement_streak == result.updated_improvement_streak == 0
    assert not result.assistance_changed


def test_missing_classification_preserves_existing_state_and_streak() -> None:
    result = select_assistance(
        None,
        previous_assistance=AssistanceLevel.HIGH,
        previous_improvement_streak=1,
    )

    assert result.selected_assistance is AssistanceLevel.HIGH
    assert result.updated_improvement_streak == 1


def test_negative_improvement_streak_is_rejected() -> None:
    with pytest.raises(ValueError, match="cannot be negative"):
        select_assistance(None, previous_improvement_streak=-1)
