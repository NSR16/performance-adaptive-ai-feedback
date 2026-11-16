from __future__ import annotations

import re
from pathlib import Path

from alembic.config import Config

from app.core.config import settings
from app.db import session as db_session
from app.models.orm import (
    AdaptiveDecision,
    EvaluationResult,
    Feedback,
    Problem,
    Student,
    StudentProblemState,
    Submission,
    TestCase,
    TestCaseResult,
)


def test_metadata_registers_all_models() -> None:
    registered = set(db_session.Base.metadata.tables)
    expected = {
        "students",
        "problems",
        "test_cases",
        "submissions",
        "evaluation_results",
        "test_case_results",
        "student_problem_states",
        "adaptive_decisions",
        "feedback",
    }
    assert expected.issubset(registered)


def test_table_constraints_and_indexes_exist() -> None:
    metadata = db_session.Base.metadata

    problems = metadata.tables["problems"]
    assert any(constraint.name == "ck_problems_difficulty" for constraint in problems.constraints)

    test_cases = metadata.tables["test_cases"]
    assert any(constraint.name == "ck_test_cases_sequence_order" for constraint in test_cases.constraints)
    assert "ix_test_cases_problem_id" in [index.name for index in test_cases.indexes]

    evaluation_results = metadata.tables["evaluation_results"]
    assert any(constraint.name == "ck_evaluation_results_status" for constraint in evaluation_results.constraints)
    assert any(constraint.name == "ck_evaluation_results_score_range" for constraint in evaluation_results.constraints)

    test_case_results = metadata.tables["test_case_results"]
    assert any(constraint.name == "uq_test_case_results_evaluation_test_case" for constraint in test_case_results.constraints)
    assert "ix_test_case_results_evaluation_id" in [index.name for index in test_case_results.indexes]

    student_problem_states = metadata.tables["student_problem_states"]
    assert any(constraint.name == "uq_student_problem_states_student_problem" for constraint in student_problem_states.constraints)

    adaptive_decisions = metadata.tables["adaptive_decisions"]
    assert any(constraint.name == "ck_adaptive_decisions_improvement_streak_nonnegative" for constraint in adaptive_decisions.constraints)

    feedback = metadata.tables["feedback"]
    assert any(constraint.name == "ck_feedback_generation_status" for constraint in feedback.constraints)


def test_relationship_definitions_match_conceptual_model() -> None:
    assert {"submissions", "student_problem_states"}.issubset(Student.__mapper__.relationships.keys())
    assert {"student", "problem"}.issubset(Submission.__mapper__.relationships.keys())
    assert {"problem", "test_case_results"}.issubset(TestCase.__mapper__.relationships.keys())
    assert {"submission", "test_case_results"}.issubset(EvaluationResult.__mapper__.relationships.keys())
    assert {"student", "problem", "adaptive_decisions"}.issubset(StudentProblemState.__mapper__.relationships.keys())
    assert {"submission", "student_problem_state", "feedback"}.issubset(AdaptiveDecision.__mapper__.relationships.keys())
    assert {"submission", "adaptive_decision"}.issubset(Feedback.__mapper__.relationships.keys())


def test_all_constraint_and_index_names_are_valid_postgres_identifiers() -> None:
    metadata = db_session.Base.metadata
    for table in metadata.tables.values():
        for constraint in table.constraints:
            if constraint.name:
                assert len(constraint.name.encode("utf-8")) <= 63, (
                    f"Constraint name exceeds PostgreSQL 63-byte limit: {constraint.name} "
                    f"({len(constraint.name.encode('utf-8'))} bytes)"
                )
        for index in table.indexes:
            if index.name:
                assert len(index.name.encode("utf-8")) <= 63, (
                    f"Index name exceeds PostgreSQL 63-byte limit: {index.name} "
                    f"({len(index.name.encode('utf-8'))} bytes)"
                )

    migration_path = Path(__file__).resolve().parents[1] / "alembic" / "versions" / "20261116_initial_schema.py"
    migration_text = migration_path.read_text(encoding="utf-8")
    for match in re.finditer(r'name="([^"]+)"', migration_text):
        name = match.group(1)
        assert len(name.encode("utf-8")) <= 63, (
            f"Migration name exceeds PostgreSQL 63-byte limit: {name} ({len(name.encode('utf-8'))} bytes)"
        )


def test_session_factory_and_settings_behaviour() -> None:
    if settings.DATABASE_URL:
        assert db_session.engine is not None
        assert db_session.SessionLocal is not None
        assert db_session.SessionLocal.kw["bind"] is db_session.engine
    else:
        assert db_session.engine is None
        assert db_session.SessionLocal is None


def test_alembic_configuration_discovers_models() -> None:
    backend_root = Path(__file__).resolve().parents[1]
    alembic_cfg = Config(str(backend_root / "alembic.ini"))
    script_location = Path(alembic_cfg.get_main_option("script_location")).resolve()
    assert script_location == (backend_root / "alembic").resolve()
    assert len(db_session.Base.metadata.tables) >= 9
