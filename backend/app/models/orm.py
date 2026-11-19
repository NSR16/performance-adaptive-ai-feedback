from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Student(Base):
    __tablename__ = "students"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    display_name: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    submissions: Mapped[list["Submission"]] = relationship(
        back_populates="student",
        cascade="save-update, merge",
    )
    student_problem_states: Mapped[list["StudentProblemState"]] = relationship(
        back_populates="student",
        cascade="save-update, merge",
    )


class Problem(Base):
    __tablename__ = "problems"
    __table_args__ = (
        CheckConstraint("difficulty IN ('EASY', 'MEDIUM', 'HARD')", name="ck_problems_difficulty"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    title: Mapped[str] = mapped_column(String(150), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    difficulty: Mapped[str] = mapped_column(String(20), nullable=False)
    starter_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    submissions: Mapped[list["Submission"]] = relationship(
        back_populates="problem",
        cascade="save-update, merge",
    )
    test_cases: Mapped[list["TestCase"]] = relationship(
        back_populates="problem",
        cascade="save-update, merge",
    )
    student_problem_states: Mapped[list["StudentProblemState"]] = relationship(
        back_populates="problem",
        cascade="save-update, merge",
    )


class TestCase(Base):
    __test__ = False
    __tablename__ = "test_cases"
    __table_args__ = (
        CheckConstraint("sequence_order >= 0", name="ck_test_cases_sequence_order"),
        Index("ix_test_cases_problem_id", "problem_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    problem_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("problems.id"), nullable=False)
    input_data: Mapped[str] = mapped_column(Text, nullable=False)
    expected_output: Mapped[str] = mapped_column(Text, nullable=False)
    is_hidden: Mapped[bool] = mapped_column(nullable=False, default=False)
    sequence_order: Mapped[int] = mapped_column(nullable=False)

    problem: Mapped[Problem] = relationship(back_populates="test_cases")
    test_case_results: Mapped[list["TestCaseResult"]] = relationship(
        back_populates="test_case",
        cascade="save-update, merge",
    )


class Submission(Base):
    __tablename__ = "submissions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    student_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("students.id"), nullable=False)
    problem_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("problems.id"), nullable=False)
    source_code: Mapped[str] = mapped_column(Text, nullable=False)
    submitted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    student: Mapped[Student] = relationship(back_populates="submissions")
    problem: Mapped[Problem] = relationship(back_populates="submissions")
    evaluation_result: Mapped["EvaluationResult | None"] = relationship(
        back_populates="submission",
        uselist=False,
        cascade="save-update, merge",
    )
    adaptive_decision: Mapped["AdaptiveDecision | None"] = relationship(
        back_populates="submission",
        uselist=False,
        cascade="save-update, merge",
    )
    feedback: Mapped["Feedback | None"] = relationship(
        back_populates="submission",
        uselist=False,
        cascade="save-update, merge",
    )

    __table_args__ = (
        Index("ix_submissions_student_problem_submitted_at", "student_id", "problem_id", "submitted_at"),
    )


class EvaluationResult(Base):
    __tablename__ = "evaluation_results"
    __table_args__ = (
        CheckConstraint("status IN ('ACCEPTED', 'WRONG_ANSWER', 'COMPILATION_ERROR', 'RUNTIME_ERROR', 'TIME_LIMIT_EXCEEDED', 'INTERNAL_ERROR')", name="ck_evaluation_results_status"),
        CheckConstraint("passed_tests >= 0", name="ck_evaluation_results_passed_tests_nonnegative"),
        CheckConstraint("total_tests >= 0", name="ck_evaluation_results_total_tests_nonnegative"),
        CheckConstraint("passed_tests <= total_tests", name="ck_evaluation_results_passed_tests_le_total"),
        CheckConstraint("score IS NULL OR (score BETWEEN 0 AND 100)", name="ck_evaluation_results_score_range"),
        CheckConstraint("execution_time_ms IS NULL OR execution_time_ms >= 0", name="ck_evaluation_results_execution_time_nonnegative"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    submission_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("submissions.id"), nullable=False, unique=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    passed_tests: Mapped[int] = mapped_column(nullable=False)
    total_tests: Mapped[int] = mapped_column(nullable=False)
    score: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    execution_time_ms: Mapped[int | None] = mapped_column(nullable=True)
    compilation_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    runtime_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    submission: Mapped[Submission] = relationship(back_populates="evaluation_result")
    test_case_results: Mapped[list["TestCaseResult"]] = relationship(
        back_populates="evaluation_result",
        cascade="save-update, merge",
    )


class TestCaseResult(Base):
    __test__ = False
    __tablename__ = "test_case_results"
    __table_args__ = (
        CheckConstraint("status IN ('PASSED', 'WRONG_ANSWER', 'RUNTIME_ERROR', 'TIME_LIMIT_EXCEEDED', 'NOT_RUN')", name="ck_test_case_results_status"),
        UniqueConstraint("evaluation_id", "test_case_id", name="uq_test_case_results_evaluation_test_case"),
        Index("ix_test_case_results_evaluation_id", "evaluation_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    evaluation_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("evaluation_results.id"), nullable=False)
    test_case_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("test_cases.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    actual_output: Mapped[str | None] = mapped_column(Text, nullable=True)
    execution_time_ms: Mapped[int | None] = mapped_column(nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    evaluation_result: Mapped[EvaluationResult] = relationship(back_populates="test_case_results")
    test_case: Mapped[TestCase] = relationship(back_populates="test_case_results")


class StudentProblemState(Base):
    __tablename__ = "student_problem_states"
    __table_args__ = (
        CheckConstraint("current_assistance IN ('HIGH', 'MODERATE', 'LOW')", name="ck_student_problem_states_current_assistance"),
        CheckConstraint("consecutive_improvements >= 0", name="ck_student_problem_states_consecutive_improvements_nonnegative"),
        UniqueConstraint("student_id", "problem_id", name="uq_student_problem_states_student_problem"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    student_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("students.id"), nullable=False)
    problem_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("problems.id"), nullable=False)
    current_assistance: Mapped[str] = mapped_column(String(10), nullable=False, server_default="MODERATE")
    consecutive_improvements: Mapped[int] = mapped_column(nullable=False, default=0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now()
    )

    student: Mapped[Student] = relationship(back_populates="student_problem_states")
    problem: Mapped[Problem] = relationship(back_populates="student_problem_states")
    adaptive_decisions: Mapped[list["AdaptiveDecision"]] = relationship(
        back_populates="student_problem_state",
        cascade="save-update, merge",
    )


class AdaptiveDecision(Base):
    __tablename__ = "adaptive_decisions"
    __table_args__ = (
        CheckConstraint("progress_classification IS NULL OR progress_classification IN ('IMPROVING', 'STAGNANT', 'REGRESSING')", name="ck_adaptive_decisions_progress_classification"),
        CheckConstraint("previous_assistance IN ('HIGH', 'MODERATE', 'LOW')", name="ck_adaptive_decisions_previous_assistance"),
        CheckConstraint("selected_assistance IN ('HIGH', 'MODERATE', 'LOW')", name="ck_adaptive_decisions_selected_assistance"),
        CheckConstraint("improvement_streak >= 0", name="ck_adaptive_decisions_improvement_streak_nonnegative"),
        Index("ix_adaptive_decisions_student_problem_state_id", "student_problem_state_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    submission_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("submissions.id"), nullable=False, unique=True)
    student_problem_state_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("student_problem_states.id", name="fk_adaptive_decisions_state"),
        nullable=False,
    )
    progress_classification: Mapped[str | None] = mapped_column(String(20), nullable=True)
    previous_assistance: Mapped[str] = mapped_column(String(10), nullable=False)
    selected_assistance: Mapped[str] = mapped_column(String(10), nullable=False)
    improvement_streak: Mapped[int] = mapped_column(nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    submission: Mapped[Submission] = relationship(back_populates="adaptive_decision")
    student_problem_state: Mapped[StudentProblemState] = relationship(back_populates="adaptive_decisions")
    feedback: Mapped["Feedback | None"] = relationship(
        back_populates="adaptive_decision",
        uselist=False,
        cascade="save-update, merge",
    )


class Feedback(Base):
    __tablename__ = "feedback"
    __table_args__ = (
        CheckConstraint("generation_status IN ('PENDING', 'SUCCEEDED', 'FAILED')", name="ck_feedback_generation_status"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    submission_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("submissions.id"), nullable=False, unique=True)
    adaptive_decision_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("adaptive_decisions.id"), nullable=False, unique=True)
    feedback_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    generation_status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="PENDING")
    model_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    submission: Mapped[Submission] = relationship(back_populates="feedback")
    adaptive_decision: Mapped[AdaptiveDecision] = relationship(back_populates="feedback")


__all__ = [
    "AdaptiveDecision",
    "EvaluationResult",
    "Feedback",
    "Problem",
    "Student",
    "StudentProblemState",
    "Submission",
    "TestCase",
    "TestCaseResult",
]
