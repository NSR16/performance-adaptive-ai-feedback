"""Initial schema for adaptive feedback and evaluation data.

Revision ID: 20261116_initial_schema
Revises:
Create Date: 2026-11-16 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "20261116_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "students",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("display_name", sa.String(length=100), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_students"),
    )

    op.create_table(
        "problems",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("title", sa.String(length=150), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("difficulty", sa.String(length=20), nullable=False),
        sa.Column("starter_code", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_problems"),
        sa.CheckConstraint("difficulty IN ('EASY', 'MEDIUM', 'HARD')", name="ck_problems_difficulty"),
    )

    op.create_table(
        "test_cases",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("problem_id", sa.BigInteger(), nullable=False),
        sa.Column("input_data", sa.Text(), nullable=False),
        sa.Column("expected_output", sa.Text(), nullable=False),
        sa.Column("is_hidden", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("sequence_order", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["problem_id"], ["problems.id"], name="fk_test_cases_problem_id_problems"),
        sa.PrimaryKeyConstraint("id", name="pk_test_cases"),
        sa.CheckConstraint("sequence_order >= 0", name="ck_test_cases_sequence_order"),
    )
    op.create_index("ix_test_cases_problem_id", "test_cases", ["problem_id"], unique=False)

    op.create_table(
        "submissions",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("student_id", sa.BigInteger(), nullable=False),
        sa.Column("problem_id", sa.BigInteger(), nullable=False),
        sa.Column("source_code", sa.Text(), nullable=False),
        sa.Column(
            "submitted_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["student_id"], ["students.id"], name="fk_submissions_student_id_students"),
        sa.ForeignKeyConstraint(["problem_id"], ["problems.id"], name="fk_submissions_problem_id_problems"),
        sa.PrimaryKeyConstraint("id", name="pk_submissions"),
    )
    op.create_index(
        "ix_submissions_student_problem_submitted_at",
        "submissions",
        ["student_id", "problem_id", "submitted_at"],
        unique=False,
    )

    op.create_table(
        "evaluation_results",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("submission_id", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("passed_tests", sa.Integer(), nullable=False),
        sa.Column("total_tests", sa.Integer(), nullable=False),
        sa.Column("score", sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column("execution_time_ms", sa.Integer(), nullable=True),
        sa.Column("compilation_error", sa.Text(), nullable=True),
        sa.Column("runtime_error", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["submission_id"], ["submissions.id"], name="fk_evaluation_results_submission_id_submissions"),
        sa.PrimaryKeyConstraint("id", name="pk_evaluation_results"),
        sa.UniqueConstraint("submission_id", name="uq_evaluation_results_submission_id"),
        sa.CheckConstraint(
            "status IN ('ACCEPTED', 'WRONG_ANSWER', 'COMPILATION_ERROR', 'RUNTIME_ERROR', 'TIME_LIMIT_EXCEEDED', 'INTERNAL_ERROR')",
            name="ck_evaluation_results_status",
        ),
        sa.CheckConstraint("passed_tests >= 0", name="ck_evaluation_results_passed_tests_nonnegative"),
        sa.CheckConstraint("total_tests >= 0", name="ck_evaluation_results_total_tests_nonnegative"),
        sa.CheckConstraint("passed_tests <= total_tests", name="ck_evaluation_results_passed_tests_le_total"),
        sa.CheckConstraint("score IS NULL OR (score BETWEEN 0 AND 100)", name="ck_evaluation_results_score_range"),
        sa.CheckConstraint("execution_time_ms IS NULL OR execution_time_ms >= 0", name="ck_evaluation_results_execution_time_nonnegative"),
    )

    op.create_table(
        "test_case_results",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("evaluation_id", sa.BigInteger(), nullable=False),
        sa.Column("test_case_id", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("actual_output", sa.Text(), nullable=True),
        sa.Column("execution_time_ms", sa.Integer(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["evaluation_id"], ["evaluation_results.id"], name="fk_test_case_results_evaluation_id_evaluation_results"),
        sa.ForeignKeyConstraint(["test_case_id"], ["test_cases.id"], name="fk_test_case_results_test_case_id_test_cases"),
        sa.PrimaryKeyConstraint("id", name="pk_test_case_results"),
        sa.UniqueConstraint("evaluation_id", "test_case_id", name="uq_test_case_results_evaluation_test_case"),
        sa.CheckConstraint(
            "status IN ('PASSED', 'WRONG_ANSWER', 'RUNTIME_ERROR', 'TIME_LIMIT_EXCEEDED', 'NOT_RUN')",
            name="ck_test_case_results_status",
        ),
    )
    op.create_index("ix_test_case_results_evaluation_id", "test_case_results", ["evaluation_id"], unique=False)

    op.create_table(
        "student_problem_states",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("student_id", sa.BigInteger(), nullable=False),
        sa.Column("problem_id", sa.BigInteger(), nullable=False),
        sa.Column("current_assistance", sa.String(length=10), nullable=False, server_default="MODERATE"),
        sa.Column("consecutive_improvements", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["student_id"], ["students.id"], name="fk_student_problem_states_student_id_students"),
        sa.ForeignKeyConstraint(["problem_id"], ["problems.id"], name="fk_student_problem_states_problem_id_problems"),
        sa.PrimaryKeyConstraint("id", name="pk_student_problem_states"),
        sa.UniqueConstraint("student_id", "problem_id", name="uq_student_problem_states_student_problem"),
        sa.CheckConstraint("current_assistance IN ('HIGH', 'MODERATE', 'LOW')", name="ck_student_problem_states_current_assistance"),
        sa.CheckConstraint("consecutive_improvements >= 0", name="ck_student_problem_states_consecutive_improvements_nonnegative"),
    )

    op.create_table(
        "adaptive_decisions",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("submission_id", sa.BigInteger(), nullable=False),
        sa.Column("student_problem_state_id", sa.BigInteger(), nullable=False),
        sa.Column("progress_classification", sa.String(length=20), nullable=True),
        sa.Column("previous_assistance", sa.String(length=10), nullable=False),
        sa.Column("selected_assistance", sa.String(length=10), nullable=False),
        sa.Column("improvement_streak", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["submission_id"], ["submissions.id"], name="fk_adaptive_decisions_submission_id_submissions"),
        sa.ForeignKeyConstraint(["student_problem_state_id"], ["student_problem_states.id"], name="fk_adaptive_decisions_state"),
        sa.PrimaryKeyConstraint("id", name="pk_adaptive_decisions"),
        sa.UniqueConstraint("submission_id", name="uq_adaptive_decisions_submission_id"),
        sa.CheckConstraint(
            "progress_classification IS NULL OR progress_classification IN ('IMPROVING', 'STAGNANT', 'REGRESSING')",
            name="ck_adaptive_decisions_progress_classification",
        ),
        sa.CheckConstraint("previous_assistance IN ('HIGH', 'MODERATE', 'LOW')", name="ck_adaptive_decisions_previous_assistance"),
        sa.CheckConstraint("selected_assistance IN ('HIGH', 'MODERATE', 'LOW')", name="ck_adaptive_decisions_selected_assistance"),
        sa.CheckConstraint("improvement_streak >= 0", name="ck_adaptive_decisions_improvement_streak_nonnegative"),
    )
    op.create_index(
        "ix_adaptive_decisions_student_problem_state_id",
        "adaptive_decisions",
        ["student_problem_state_id"],
        unique=False,
    )

    op.create_table(
        "feedback",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("submission_id", sa.BigInteger(), nullable=False),
        sa.Column("adaptive_decision_id", sa.BigInteger(), nullable=False),
        sa.Column("feedback_text", sa.Text(), nullable=True),
        sa.Column("generation_status", sa.String(length=20), nullable=False, server_default="PENDING"),
        sa.Column("model_name", sa.String(length=100), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["submission_id"], ["submissions.id"], name="fk_feedback_submission_id_submissions"),
        sa.ForeignKeyConstraint(["adaptive_decision_id"], ["adaptive_decisions.id"], name="fk_feedback_adaptive_decision_id_adaptive_decisions"),
        sa.PrimaryKeyConstraint("id", name="pk_feedback"),
        sa.UniqueConstraint("submission_id", name="uq_feedback_submission_id"),
        sa.UniqueConstraint("adaptive_decision_id", name="uq_feedback_adaptive_decision_id"),
        sa.CheckConstraint("generation_status IN ('PENDING', 'SUCCEEDED', 'FAILED')", name="ck_feedback_generation_status"),
    )


def downgrade() -> None:
    op.drop_table("feedback")
    op.drop_table("adaptive_decisions")
    op.drop_table("student_problem_states")
    op.drop_table("test_case_results")
    op.drop_table("evaluation_results")
    op.drop_table("submissions")
    op.drop_table("test_cases")
    op.drop_table("problems")
    op.drop_table("students")
