from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

TestCaseStatus = Literal[
    "PASSED",
    "WRONG_ANSWER",
    "RUNTIME_ERROR",
    "TIME_LIMIT_EXCEEDED",
    "NOT_RUN",
]
EvaluationStatus = Literal[
    "ACCEPTED",
    "WRONG_ANSWER",
    "COMPILATION_ERROR",
    "RUNTIME_ERROR",
    "TIME_LIMIT_EXCEEDED",
    "INTERNAL_ERROR",
]


@dataclass(frozen=True)
class TestCaseInput:
    __test__ = False

    test_case_id: int
    input_data: str
    expected_output: str
    is_hidden: bool
    sequence_order: int


@dataclass(frozen=True)
class TestCaseResult:
    test_case_id: int
    status: TestCaseStatus
    actual_output: str | None = None
    execution_time_ms: int | None = None
    error_message: str | None = None


@dataclass(frozen=True)
class EvaluationResult:
    status: EvaluationStatus
    passed_tests: int
    total_tests: int
    score: Decimal | None
    execution_time_ms: int | None
    compilation_error: str | None
    runtime_error: str | None
    test_case_results: list[TestCaseResult]
    internal_error: str | None = None
