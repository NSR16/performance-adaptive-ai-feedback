from __future__ import annotations

from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import BigInteger, create_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models.orm import Problem, Student, TestCase
from app.services.evaluation.schemas import (
    EvaluationResult,
    TestCaseResult as EvaluationTestCaseResult,
)
from app.services.feedback import FeedbackGenerationResult
from app.services.submissions import SubmissionWorkflow
from app.api.routes.submissions import get_submission_workflow
from scripts.seed_demo import seed_demo_data


@compiles(BigInteger, "sqlite")
def compile_sqlite_big_integer(element, compiler, **kwargs):
    return "INTEGER"


class MockEvaluationEngine:
    def evaluate(self, source_code: str, test_cases: list) -> EvaluationResult:
        if "INTERNAL_FAILURE" in source_code:
            raise RuntimeError("mock infrastructure failure")
        if "COMPILATION_ERROR" in source_code:
            return EvaluationResult(
                status="COMPILATION_ERROR",
                passed_tests=0,
                total_tests=len(test_cases),
                score=None,
                execution_time_ms=0,
                compilation_error="mock compiler diagnostic",
                runtime_error=None,
                test_case_results=[
                    EvaluationTestCaseResult(
                        test_case_id=case.test_case_id,
                        status="NOT_RUN",
                    )
                    for case in test_cases
                ],
            )

        score = Decimal("40")
        for marker in ("score40", "score65", "score85", "score60"):
            if marker in source_code:
                score = Decimal(marker.removeprefix("score"))
                break

        passed = round(float(score) * len(test_cases) / 100)
        statuses = [
            "PASSED" if index < passed else "WRONG_ANSWER"
            for index in range(len(test_cases))
        ]
        return EvaluationResult(
            status="ACCEPTED" if passed == len(test_cases) else "WRONG_ANSWER",
            passed_tests=passed,
            total_tests=len(test_cases),
            score=score,
            execution_time_ms=10,
            compilation_error=None,
            runtime_error=None,
            test_case_results=[
                EvaluationTestCaseResult(
                    test_case_id=case.test_case_id,
                    status=statuses[index],
                )
                for index, case in enumerate(test_cases)
            ],
        )


class MockFeedbackGenerator:
    def __init__(self, fail: bool = False) -> None:
        self.fail = fail

    async def generate_feedback(self, **kwargs: object) -> FeedbackGenerationResult:
        if self.fail:
            return FeedbackGenerationResult(
                feedback_text=None,
                model_name="qwen2.5:3b",
                generation_status="FAILED",
                error_message="mock Ollama unavailable",
            )
        return FeedbackGenerationResult(
            feedback_text="Mock grounded hint",
            model_name="qwen2.5:3b",
            generation_status="SUCCEEDED",
        )


@pytest.fixture
def api_database(monkeypatch: pytest.MonkeyPatch):
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    TestingSession = sessionmaker(
        bind=engine,
        autocommit=False,
        autoflush=False,
        expire_on_commit=False,
    )

    with TestingSession() as db:
        student = Student(id=1, display_name="Demo Student")
        problem = Problem(
            id=1,
            title="Sum Two Integers",
            description="Read two integers and print their sum.",
            difficulty="EASY",
            starter_code="public class Main {}",
        )
        db.add_all([student, problem])
        db.flush()
        db.add_all(
            [
                TestCase(
                    problem_id=1,
                    input_data="1 2\n",
                    expected_output="3",
                    is_hidden=False,
                    sequence_order=1,
                ),
                TestCase(
                    problem_id=1,
                    input_data="10 25\n",
                    expected_output="35",
                    is_hidden=False,
                    sequence_order=2,
                ),
                TestCase(
                    problem_id=1,
                    input_data="-4 9\n",
                    expected_output="5",
                    is_hidden=True,
                    sequence_order=3,
                ),
            ]
        )
        db.commit()

    def override_get_db():
        with TestingSession() as db:
            yield db

    def override_workflow():
        db = TestingSession()
        try:
            yield SubmissionWorkflow(
                db=db,
                engine=MockEvaluationEngine(),
                feedback_generator=MockFeedbackGenerator(),
            )
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_submission_workflow] = override_workflow

    with TestClient(app) as client:
        yield client, TestingSession

    app.dependency_overrides.clear()
    Base.metadata.drop_all(engine)
    engine.dispose()


def test_health_and_problem_retrieval(api_database) -> None:
    client, _ = api_database

    assert client.get("/health").json() == {"status": "ok"}
    problems = client.get("/api/problems")
    assert problems.status_code == 200
    assert problems.json()[0]["title"] == "Sum Two Integers"

    detail = client.get("/api/problems/1")
    assert detail.status_code == 200
    assert detail.json()["hidden_test_case_count"] == 1
    assert len(detail.json()["public_test_cases"]) == 2
    assert "35" in str(detail.json())


def test_student_list_returns_only_frontend_fields(api_database) -> None:
    client, TestingSession = api_database
    with TestingSession() as db:
        db.add(Student(id=2, display_name="Second Demo Student"))
        db.commit()

    response = client.get("/api/students")

    assert response.status_code == 200
    assert response.json() == [
        {"id": 1, "display_name": "Demo Student"},
        {"id": 2, "display_name": "Second Demo Student"},
    ]


def test_demo_seed_is_idempotent_and_creates_three_students(api_database) -> None:
    _, TestingSession = api_database

    with TestingSession() as db:
        seed_demo_data(db)
        seed_demo_data(db)

        students = db.query(Student).order_by(Student.id).all()

    assert [student.display_name for student in students] == [
        "Demo Student",
        "Demo Student 2",
        "Demo Student 3",
    ]


def test_invalid_submission_requests(api_database) -> None:
    client, _ = api_database

    assert client.post(
        "/api/submissions",
        json={"student_id": 1, "problem_id": 1, "source_code": ""},
    ).status_code == 422
    assert client.post(
        "/api/submissions",
        json={"student_id": 0, "problem_id": 1, "source_code": "code"},
    ).status_code == 422


def test_missing_student_and_problem(api_database) -> None:
    client, _ = api_database

    assert client.post(
        "/api/submissions",
        json={"student_id": 999, "problem_id": 1, "source_code": "code"},
    ).status_code == 404
    assert client.post(
        "/api/submissions",
        json={"student_id": 1, "problem_id": 999, "source_code": "code"},
    ).status_code == 404


def test_missing_test_cases(api_database) -> None:
    client, TestingSession = api_database
    with TestingSession() as db:
        db.add(
            Problem(
                id=2,
                title="Empty",
                description="No test cases.",
                difficulty="EASY",
            )
        )
        db.commit()

    response = client.post(
        "/api/submissions",
        json={"student_id": 1, "problem_id": 2, "source_code": "code"},
    )
    assert response.status_code == 422
    assert "no test cases" in response.json()["detail"].lower()


def test_first_submission_is_baseline_and_persists_data(api_database) -> None:
    client, TestingSession = api_database

    response = client.post(
        "/api/submissions",
        json={"student_id": 1, "problem_id": 1, "source_code": "score40"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["submission_id"] > 0
    assert body["test_case_results"] == [
        {
            "sequence_order": 1,
            "status": "PASSED",
            "execution_time_ms": None,
        },
        {
            "sequence_order": 2,
            "status": "WRONG_ANSWER",
            "execution_time_ms": None,
        },
        {
            "sequence_order": 3,
            "status": "WRONG_ANSWER",
            "execution_time_ms": None,
        },
    ]
    assert body["progress_classification"] is None
    assert body["selected_assistance_level"] == "MODERATE"
    assert body["feedback_text"] == "Mock grounded hint"
    assert body["generation_status"] == "SUCCEEDED"

    detail = client.get(f"/api/submissions/{body['submission_id']}")
    assert detail.status_code == 200
    assert detail.json()["progress_classification"] is None
    assert detail.json()["feedback_generation_status"] == "SUCCEEDED"
    assert detail.json()["test_case_results"] == body["test_case_results"]
    assert all(
        set(test_case) == {"sequence_order", "status", "execution_time_ms"}
        for test_case in detail.json()["test_case_results"]
    )

    from app.models.orm import Feedback, StudentProblemState

    with TestingSession() as db:
        state = db.query(StudentProblemState).one()
        assert state.current_assistance == "MODERATE"
        assert state.consecutive_improvements == 0
        assert db.query(Feedback).count() == 1


def test_second_submission_improves_then_fsm_reduces_assistance(api_database) -> None:
    client, TestingSession = api_database

    first = client.post(
        "/api/submissions",
        json={"student_id": 1, "problem_id": 1, "source_code": "score40"},
    ).json()
    second = client.post(
        "/api/submissions",
        json={"student_id": 1, "problem_id": 1, "source_code": "score65"},
    ).json()
    third = client.post(
        "/api/submissions",
        json={"student_id": 1, "problem_id": 1, "source_code": "score85"},
    ).json()

    assert first["progress_classification"] is None
    assert second["progress_classification"] == "IMPROVING"
    assert second["selected_assistance_level"] == "MODERATE"
    assert third["progress_classification"] == "IMPROVING"
    assert third["selected_assistance_level"] == "LOW"

    from app.models.orm import StudentProblemState

    with TestingSession() as db:
        state = db.query(StudentProblemState).one()
        assert state.consecutive_improvements == 2
        assert state.current_assistance == "LOW"


def test_student_history_and_adaptive_state_are_isolated(api_database) -> None:
    client, TestingSession = api_database
    with TestingSession() as db:
        db.add(Student(id=2, display_name="Second Demo Student"))
        db.commit()

    for score in ("score40", "score65", "score85"):
        response = client.post(
            "/api/submissions",
            json={"student_id": 1, "problem_id": 1, "source_code": score},
        )
        assert response.status_code == 200
    second_student_response = client.post(
        "/api/submissions",
        json={"student_id": 2, "problem_id": 1, "source_code": "score65"},
    )

    assert second_student_response.status_code == 200
    assert second_student_response.json()["progress_classification"] is None
    assert second_student_response.json()["selected_assistance_level"] == "MODERATE"
    assert len(client.get("/api/students/1/problems/1/history").json()) == 3
    assert len(client.get("/api/students/2/problems/1/history").json()) == 1

    from app.models.orm import StudentProblemState

    with TestingSession() as db:
        states = {
            state.student_id: state
            for state in db.query(StudentProblemState).all()
        }
    assert states[1].current_assistance == "LOW"
    assert states[1].consecutive_improvements == 2
    assert states[2].current_assistance == "MODERATE"
    assert states[2].consecutive_improvements == 0


def test_ollama_failure_preserves_evaluation_and_adaptive_data(api_database) -> None:
    client, TestingSession = api_database

    def override_failed_workflow():
        db = TestingSession()
        try:
            yield SubmissionWorkflow(
                db=db,
                engine=MockEvaluationEngine(),
                feedback_generator=MockFeedbackGenerator(fail=True),
            )
        finally:
            db.close()

    app.dependency_overrides[get_submission_workflow] = override_failed_workflow

    response = client.post(
        "/api/submissions",
        json={"student_id": 1, "problem_id": 1, "source_code": "score40"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["generation_status"] == "FAILED"
    assert body["error_message"] == "mock Ollama unavailable"
    assert body["evaluation_status"] == "WRONG_ANSWER"

    from app.models.orm import AdaptiveDecision, EvaluationResult as OrmEvaluationResult

    with TestingSession() as db:
        assert db.query(OrmEvaluationResult).count() == 1
        assert db.query(AdaptiveDecision).count() == 1


def test_compilation_error_is_valid_submission(api_database) -> None:
    client, _ = api_database

    response = client.post(
        "/api/submissions",
        json={
            "student_id": 1,
            "problem_id": 1,
            "source_code": "COMPILATION_ERROR",
        },
    )
    assert response.status_code == 200
    assert response.json()["evaluation_status"] == "COMPILATION_ERROR"
    assert response.json()["score"] is None
    assert response.json()["progress_classification"] is None


def test_evaluation_infrastructure_exception_is_api_error(api_database) -> None:
    client, TestingSession = api_database

    def override_infrastructure_failure():
        db = TestingSession()
        try:
            yield SubmissionWorkflow(
                db=db,
                engine=MockEvaluationEngine(),
                feedback_generator=MockFeedbackGenerator(),
            )
        finally:
            db.close()

    app.dependency_overrides[get_submission_workflow] = override_infrastructure_failure
    response = client.post(
        "/api/submissions",
        json={
            "student_id": 1,
            "problem_id": 1,
            "source_code": "INTERNAL_FAILURE",
        },
    )
    assert response.status_code == 500
    assert "Evaluation infrastructure failed" in response.json()["detail"]


def test_history_is_chronological(api_database) -> None:
    client, _ = api_database

    client.post(
        "/api/submissions",
        json={"student_id": 1, "problem_id": 1, "source_code": "score40"},
    )
    client.post(
        "/api/submissions",
        json={"student_id": 1, "problem_id": 1, "source_code": "score65"},
    )

    response = client.get("/api/students/1/problems/1/history")
    assert response.status_code == 200
    history = response.json()
    assert len(history) == 2
    assert history[0]["submission_id"] < history[1]["submission_id"]
    assert history[0]["progress_classification"] is None
    assert history[1]["progress_classification"] == "IMPROVING"


def test_history_returns_404_for_unknown_student(api_database) -> None:
    client, _ = api_database

    response = client.get("/api/students/999/problems/1/history")

    assert response.status_code == 404
    assert response.json()["detail"] == "Student not found."


def test_history_returns_404_for_unknown_problem(api_database) -> None:
    client, _ = api_database

    response = client.get("/api/students/1/problems/999/history")

    assert response.status_code == 404
    assert response.json()["detail"] == "Problem not found."


def test_history_returns_empty_list_for_existing_pair_without_submissions(
    api_database,
) -> None:
    client, _ = api_database

    response = client.get("/api/students/1/problems/1/history")

    assert response.status_code == 200
    assert response.json() == []
