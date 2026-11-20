from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from app.services.progress.analyzer import ProgressClassification


class AssistanceLevel(str, Enum):
    HIGH = "HIGH"
    MODERATE = "MODERATE"
    LOW = "LOW"


INITIAL_ASSISTANCE_LEVEL = AssistanceLevel.LOW


@dataclass(frozen=True)
class AdaptiveDecision:
    previous_assistance: AssistanceLevel
    selected_assistance: AssistanceLevel
    progress_classification: ProgressClassification | None
    previous_improvement_streak: int
    updated_improvement_streak: int
    assistance_changed: bool


def select_assistance(
    progress_classification: ProgressClassification | None,
    previous_assistance: AssistanceLevel = INITIAL_ASSISTANCE_LEVEL,
    previous_improvement_streak: int = 0,
) -> AdaptiveDecision:
    """Return a deterministic assistance decision without accessing persistence."""
    if previous_improvement_streak < 0:
        raise ValueError("The previous improvement streak cannot be negative.")
    if progress_classification is not None and not isinstance(
        progress_classification, ProgressClassification
    ):
        raise TypeError(
            "The progress classification must be a ProgressClassification or None."
        )

    if progress_classification is None:
        selected_assistance = previous_assistance
        updated_streak = previous_improvement_streak
    elif progress_classification is ProgressClassification.IMPROVING:
        updated_streak = previous_improvement_streak + 1
        selected_assistance = previous_assistance
        if updated_streak >= 2:
            selected_assistance = _improvement_transition(previous_assistance)
            if selected_assistance is not previous_assistance:
                updated_streak = 0
    else:
        updated_streak = 0
        selected_assistance = _transition(previous_assistance, progress_classification)

    return AdaptiveDecision(
        previous_assistance=previous_assistance,
        selected_assistance=selected_assistance,
        progress_classification=progress_classification,
        previous_improvement_streak=previous_improvement_streak,
        updated_improvement_streak=updated_streak,
        assistance_changed=selected_assistance is not previous_assistance,
    )


def _improvement_transition(state: AssistanceLevel) -> AssistanceLevel:
    if state is AssistanceLevel.HIGH:
        return AssistanceLevel.MODERATE
    if state is AssistanceLevel.MODERATE:
        return AssistanceLevel.LOW
    return AssistanceLevel.LOW


def _transition(
    state: AssistanceLevel,
    classification: ProgressClassification,
) -> AssistanceLevel:
    if classification is ProgressClassification.STAGNANT:
        if state is AssistanceLevel.LOW:
            return AssistanceLevel.MODERATE
        return state
    if classification is ProgressClassification.REGRESSING:
        return AssistanceLevel.HIGH
    return state
