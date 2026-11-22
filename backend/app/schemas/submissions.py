from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from app.services.evaluation.schemas import TestCaseStatus


class SubmissionCreate(BaseModel):
    student_id: int = Field(gt=0)
    problem_id: int = Field(gt=0)
    source_code: str = Field(min_length=1, max_length=50000)


class StudentSummary(BaseModel):
    id: int
    display_name: str


class ProblemSummary(BaseModel):
    id: int
    title: str
    difficulty: str


class PublicTestCase(BaseModel):
    id: int
    input_data: str
    expected_output: str
    sequence_order: int


class ProblemDetail(BaseModel):
    id: int
    title: str
    description: str
    difficulty: str
    starter_code: str | None
    public_test_cases: list[PublicTestCase]
    hidden_test_case_count: int


class SubmissionTestCaseResult(BaseModel):
    sequence_order: int
    status: TestCaseStatus
    execution_time_ms: int | None


class SubmissionResponse(BaseModel):
    submission_id: int
    evaluation_status: str
    passed_tests: int
    total_tests: int
    score: Decimal | None
    progress_classification: str | None
    selected_assistance_level: str
    feedback_text: str | None = None
    generation_status: str
    model_name: str | None = None
    error_message: str | None = None
    test_case_results: list[SubmissionTestCaseResult]


class SubmissionDetail(BaseModel):
    submission_id: int
    student_id: int
    problem_id: int
    submitted_at: datetime
    source_code: str
    evaluation_status: str | None
    passed_tests: int | None
    total_tests: int | None
    score: Decimal | None
    progress_classification: str | None
    selected_assistance_level: str | None
    improvement_streak: int | None
    feedback_text: str | None
    feedback_generation_status: str | None
    feedback_error_message: str | None
    model_name: str | None
    test_case_results: list[SubmissionTestCaseResult]


class HistoryItem(BaseModel):
    submission_id: int
    submitted_at: datetime
    evaluation_status: str | None
    passed_tests: int | None
    total_tests: int | None
    score: Decimal | None
    progress_classification: str | None
    selected_assistance_level: str | None


class HistoryResetResponse(BaseModel):
    student_id: int
    problem_id: int
    deleted_submissions: int
