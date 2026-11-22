from __future__ import annotations

from datetime import timedelta
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
from app.models.orm import Problem, Student, Submission, TestCase
from app.services.evaluation.schemas import (
    EvaluationResult,
    TestCaseResult as EvaluationTestCaseResult,
)
from app.services.evaluation.engine import EvaluationEngine
from app.services.feedback import FeedbackGenerationResult
from app.services.evaluation.java_runner import JavaRunner, ProcessResult
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


def test_demo_seed_is_idempotent_and_creates_demo_bank(api_database) -> None:
    _, TestingSession = api_database

    with TestingSession() as db:
        existing_problem = Problem(
            id=2,
            title="Demo: Sum Two Integers",
            description="Read two integers from standard input and print their sum.",
            difficulty="EASY",
            starter_code="public class Main {}",
        )
        db.add(existing_problem)
        db.flush()
        existing_test_cases = [
            TestCase(
                problem_id=existing_problem.id,
                input_data=input_data,
                expected_output=expected_output,
                is_hidden=is_hidden,
                sequence_order=sequence,
            )
            for input_data, expected_output, is_hidden, sequence in (
                ("1 2\n", "3", False, 1),
                ("10 25\n", "35", False, 2),
                ("-4 9\n", "5", True, 3),
                ("0 0\n", "0", True, 4),
            )
        ]
        db.add_all(existing_test_cases)
        historical_submission = Submission(
            id=1,
            student_id=1,
            problem_id=existing_problem.id,
            source_code="historical source",
        )
        db.add(historical_submission)
        db.commit()
        original_test_case_ids = [case.id for case in existing_test_cases]

        seed_demo_data(db)
        after_first_problem_count = db.query(Problem).count()
        after_first_test_case_count = db.query(TestCase).count()
        seed_demo_data(db)

        students = db.query(Student).order_by(Student.id).all()
        problems = db.query(Problem).order_by(Problem.id).all()
        test_cases = db.query(TestCase).all()
        updated_problem = db.get(Problem, existing_problem.id)
        retained_test_case_ids = [
            case.id
            for case in db.query(TestCase)
            .filter(TestCase.problem_id == existing_problem.id)
            .order_by(TestCase.sequence_order)
        ]
        retained_submission = db.get(Submission, historical_submission.id)
        assert db.query(Problem).count() == after_first_problem_count
        assert db.query(TestCase).count() == after_first_test_case_count

    assert updated_problem is not None
    assert updated_problem.id == existing_problem.id
    assert "Input format:" in updated_problem.description
    assert "Output format:" in updated_problem.description
    assert "Constraints:" in updated_problem.description
    assert "Example input:" in updated_problem.description
    assert "Example output:" in updated_problem.description
    assert retained_test_case_ids == original_test_case_ids
    assert retained_submission is not None
    assert retained_submission.problem_id == existing_problem.id
    assert [student.display_name for student in students] == [
        "Demo Student",
        "Demo Student 2",
        "Demo Student 3",
    ]
    assert len(problems) >= 6
    assert len(test_cases) >= 26
    assert {
        "Demo: Sum Two Integers",
        "Even or Odd",
        "Largest of Three Numbers",
        "Calculate Factorial",
        "Sum of Array Elements",
        "Prime Number Checker",
    }.issubset({problem.title for problem in problems})


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
    assert body["selected_assistance_level"] == "LOW"
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
        assert state.current_assistance == "LOW"
        assert state.consecutive_improvements == 0
        assert db.query(Feedback).count() == 1


def test_improving_submissions_keep_new_student_problem_state_low(api_database) -> None:
    client, TestingSession = api_database

    first = client.post(
        "/api/submissions",
        json={"student_id": 1, "problem_id": 1, "source_code": "score40"},
    ).json()
    second = client.post(
        "/api/submissions",
        json={"student_id": 1, "problem_id": 1, "source_code": "score65"},
    ).json()

    assert first["progress_classification"] is None
    assert first["selected_assistance_level"] == "LOW"
    assert second["progress_classification"] == "IMPROVING"
    assert second["selected_assistance_level"] == "LOW"

    from app.models.orm import StudentProblemState

    with TestingSession() as db:
        state = db.query(StudentProblemState).one()
        assert state.current_assistance == "LOW"
        assert state.consecutive_improvements == 1

    third = client.post(
        "/api/submissions",
        json={"student_id": 1, "problem_id": 1, "source_code": "score85"},
    ).json()

    assert third["progress_classification"] == "IMPROVING"
    assert third["selected_assistance_level"] == "LOW"

    with TestingSession() as db:
        state = db.query(StudentProblemState).one()
        assert state.consecutive_improvements == 2
        assert state.current_assistance == "LOW"


def test_stagnant_second_submission_increases_low_assistance(api_database) -> None:
    client, TestingSession = api_database

    first = client.post(
        "/api/submissions",
        json={"student_id": 1, "problem_id": 1, "source_code": "score40"},
    ).json()
    second = client.post(
        "/api/submissions",
        json={"student_id": 1, "problem_id": 1, "source_code": "score40"},
    ).json()

    assert first["progress_classification"] is None
    assert first["selected_assistance_level"] == "LOW"
    assert second["progress_classification"] == "STAGNANT"
    assert second["selected_assistance_level"] == "MODERATE"

    from app.models.orm import StudentProblemState

    with TestingSession() as db:
        state = db.query(StudentProblemState).one()
        assert state.current_assistance == "MODERATE"
        assert state.consecutive_improvements == 0


def test_student_problem_states_are_independent_and_restored(api_database) -> None:
    client, TestingSession = api_database
    with TestingSession() as db:
        db.add(
            Problem(
                id=2,
                title="Second Problem",
                description="A second problem for the same student.",
                difficulty="EASY",
            )
        )
        db.flush()
        db.add(
            TestCase(
                problem_id=2,
                input_data="1 2\n",
                expected_output="3",
                is_hidden=False,
                sequence_order=1,
            )
        )
        db.commit()

    first_problem_first = client.post(
        "/api/submissions",
        json={"student_id": 1, "problem_id": 1, "source_code": "score65"},
    ).json()
    first_problem_second = client.post(
        "/api/submissions",
        json={"student_id": 1, "problem_id": 1, "source_code": "score40"},
    ).json()
    second_problem_first = client.post(
        "/api/submissions",
        json={"student_id": 1, "problem_id": 2, "source_code": "score65"},
    ).json()
    first_problem_return = client.post(
        "/api/submissions",
        json={"student_id": 1, "problem_id": 1, "source_code": "score40"},
    ).json()

    assert first_problem_first["progress_classification"] is None
    assert first_problem_first["selected_assistance_level"] == "LOW"
    assert first_problem_second["progress_classification"] == "REGRESSING"
    assert first_problem_second["selected_assistance_level"] == "HIGH"
    assert second_problem_first["progress_classification"] is None
    assert second_problem_first["selected_assistance_level"] == "LOW"
    assert first_problem_return["progress_classification"] == "STAGNANT"
    assert first_problem_return["selected_assistance_level"] == "HIGH"

    from app.models.orm import StudentProblemState

    with TestingSession() as db:
        states = {
            state.problem_id: state
            for state in db.query(StudentProblemState).all()
        }
    assert states[1].current_assistance == "HIGH"
    assert states[1].consecutive_improvements == 0
    assert states[2].current_assistance == "LOW"
    assert states[2].consecutive_improvements == 0


def test_scoped_history_reset_preserves_other_histories(api_database) -> None:
    client, TestingSession = api_database
    with TestingSession() as db:
        db.add(Student(id=2, display_name="Second Demo Student"))
        db.add(
            Problem(
                id=2,
                title="Second Problem",
                description="A second problem for scoped reset testing.",
                difficulty="EASY",
            )
        )
        db.flush()
        db.add(
            TestCase(
                problem_id=2,
                input_data="1\n",
                expected_output="1",
                is_hidden=False,
                sequence_order=1,
            )
        )
        db.commit()

    for payload in (
        {"student_id": 1, "problem_id": 1, "source_code": "score40"},
        {"student_id": 1, "problem_id": 1, "source_code": "score65"},
        {"student_id": 2, "problem_id": 1, "source_code": "score40"},
        {"student_id": 1, "problem_id": 2, "source_code": "score40"},
    ):
        response = client.post("/api/submissions", json=payload)
        assert response.status_code == 200

    response = client.delete("/api/students/1/problems/1/history")
    assert response.status_code == 200
    assert response.json() == {
        "student_id": 1,
        "problem_id": 1,
        "deleted_submissions": 2,
    }

    assert client.get("/api/students/1/problems/1/history").json() == []
    assert len(client.get("/api/students/2/problems/1/history").json()) == 1
    assert len(client.get("/api/students/1/problems/2/history").json()) == 1

    from app.models.orm import (
        AdaptiveDecision,
        EvaluationResult,
        Feedback,
        StudentProblemState,
        Submission,
        TestCaseResult,
    )

    with TestingSession() as db:
        assert db.query(Submission).filter_by(student_id=1, problem_id=1).count() == 0
        assert db.query(StudentProblemState).filter_by(student_id=1, problem_id=1).count() == 0
        assert db.query(Submission).filter_by(student_id=2, problem_id=1).count() == 1
        assert db.query(Submission).filter_by(student_id=1, problem_id=2).count() == 1
        assert db.query(StudentProblemState).count() == 2
        assert db.query(EvaluationResult).count() == 2
        assert db.query(TestCaseResult).count() >= 2
        assert db.query(AdaptiveDecision).count() == 2
        assert db.query(Feedback).count() == 2


def test_student_history_and_adaptive_state_are_isolated(api_database) -> None:
    client, TestingSession = api_database
    with TestingSession() as db:
        db.add(Student(id=2, display_name="Second Demo Student"))
        db.commit()

    def submit(student_id: int, source_code: str) -> dict:
        response = client.post(
            "/api/submissions",
            json={
                "student_id": student_id,
                "problem_id": 1,
                "source_code": source_code,
            },
        )
        assert response.status_code == 200
        return response.json()

    student_one_first = submit(1, "score40")
    student_one_stagnant = submit(1, "score40")
    assert student_one_first["progress_classification"] is None
    assert student_one_first["selected_assistance_level"] == "LOW"
    assert student_one_stagnant["progress_classification"] == "STAGNANT"
    assert student_one_stagnant["selected_assistance_level"] == "MODERATE"

    from app.models.orm import StudentProblemState

    with TestingSession() as db:
        student_one_state = db.query(StudentProblemState).filter_by(student_id=1).one()
        assert student_one_state.current_assistance == "MODERATE"
        assert student_one_state.consecutive_improvements == 0

    student_two_first = submit(2, "score40")
    student_two_second = submit(2, "score65")
    assert student_two_first["progress_classification"] is None
    assert student_two_first["selected_assistance_level"] == "LOW"
    assert student_two_second["progress_classification"] == "IMPROVING"
    assert student_two_second["selected_assistance_level"] == "LOW"

    with TestingSession() as db:
        states = {
            state.student_id: (state.current_assistance, state.consecutive_improvements)
            for state in db.query(StudentProblemState).all()
        }
    assert states == {1: ("MODERATE", 0), 2: ("LOW", 1)}

    student_one_third = submit(1, "score65")
    assert student_one_third["progress_classification"] == "IMPROVING"
    assert student_one_third["selected_assistance_level"] == "MODERATE"
    with TestingSession() as db:
        states = {
            state.student_id: (state.current_assistance, state.consecutive_improvements)
            for state in db.query(StudentProblemState).all()
        }
    assert states == {1: ("MODERATE", 1), 2: ("LOW", 1)}

    student_two_third = submit(2, "score85")
    assert student_two_third["progress_classification"] == "IMPROVING"
    assert student_two_third["selected_assistance_level"] == "LOW"
    with TestingSession() as db:
        states = {
            state.student_id: (state.current_assistance, state.consecutive_improvements)
            for state in db.query(StudentProblemState).all()
        }
    assert states == {1: ("MODERATE", 1), 2: ("LOW", 2)}

    student_one_history = client.get("/api/students/1/problems/1/history").json()
    student_two_history = client.get("/api/students/2/problems/1/history").json()
    assert {
        item["submission_id"] for item in student_one_history
    } == {
        student_one_first["submission_id"],
        student_one_stagnant["submission_id"],
        student_one_third["submission_id"],
    }
    assert {
        item["submission_id"] for item in student_two_history
    } == {
        student_two_first["submission_id"],
        student_two_second["submission_id"],
        student_two_third["submission_id"],
    }


@pytest.mark.parametrize(
    ("assistance", "streak"),
    [
        ("MODERATE", 1),
        ("HIGH", 1),
    ],
)
def test_existing_student_problem_state_is_not_overwritten(
    api_database,
    assistance: str,
    streak: int,
) -> None:
    client, TestingSession = api_database

    from app.models.orm import StudentProblemState

    with TestingSession() as db:
        db.add(
            StudentProblemState(
                student_id=1,
                problem_id=1,
                current_assistance=assistance,
                consecutive_improvements=streak,
            )
        )
        db.commit()

    response = client.post(
        "/api/submissions",
        json={"student_id": 1, "problem_id": 1, "source_code": "score40"},
    ).json()

    assert response["progress_classification"] is None
    assert response["selected_assistance_level"] == assistance
    with TestingSession() as db:
        state = db.query(StudentProblemState).one()
        assert state.current_assistance == assistance
        assert state.consecutive_improvements == streak


def test_database_default_for_student_problem_state_is_low(api_database) -> None:
    _, TestingSession = api_database

    from app.models.orm import StudentProblemState

    with TestingSession() as db:
        db.add(StudentProblemState(student_id=1, problem_id=1))
        db.commit()
        state = db.query(StudentProblemState).one()

    assert state.current_assistance == "LOW"
    assert state.consecutive_improvements == 0


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


def test_internal_evaluation_error_does_not_change_adaptive_state(
    api_database,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, TestingSession = api_database
    first = client.post(
        "/api/submissions",
        json={"student_id": 1, "problem_id": 1, "source_code": "score40"},
    ).json()

    from app.models.orm import StudentProblemState

    with TestingSession() as db:
        state = db.query(StudentProblemState).one()
        state.current_assistance = "MODERATE"
        state.consecutive_improvements = 1
        db.commit()

    runner = JavaRunner()
    monkeypatch.setattr(
        runner,
        "compile",
        lambda source_code, work_dir, class_name: ProcessResult(0, "", "", 0),
    )
    executions = 0

    def fail_second_execution(
        work_dir: object,
        class_name: str,
        input_data: str,
        timeout: float,
    ) -> ProcessResult:
        nonlocal executions
        executions += 1
        if executions == 2:
            raise OSError("runtime unavailable")
        return ProcessResult(0, "3\n", "", 10)

    monkeypatch.setattr(runner, "execute", fail_second_execution)

    def override_internal_error_workflow():
        db = TestingSession()
        try:
            yield SubmissionWorkflow(
                db=db,
                engine=EvaluationEngine(runner=runner),
                feedback_generator=MockFeedbackGenerator(),
            )
        finally:
            db.close()

    app.dependency_overrides[get_submission_workflow] = (
        override_internal_error_workflow
    )
    response = client.post(
        "/api/submissions",
        json={"student_id": 1, "problem_id": 1, "source_code": "RUNTIME_FAILURE"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["evaluation_status"] == "INTERNAL_ERROR"
    assert body["score"] is None
    assert body["progress_classification"] is None
    assert body["selected_assistance_level"] == "MODERATE"

    from app.models.orm import (
        AdaptiveDecision,
        EvaluationResult as OrmEvaluationResult,
        TestCaseResult as OrmTestCaseResult,
    )

    with TestingSession() as db:
        evaluation = (
            db.query(OrmEvaluationResult)
            .filter(OrmEvaluationResult.submission_id == body["submission_id"])
            .one()
        )
        adaptive = (
            db.query(AdaptiveDecision)
            .filter(AdaptiveDecision.submission_id == body["submission_id"])
            .one()
        )
        results = (
            db.query(OrmTestCaseResult)
            .filter(OrmTestCaseResult.evaluation_id == evaluation.id)
            .order_by(OrmTestCaseResult.id)
            .all()
        )
        state = db.query(StudentProblemState).one()

    assert evaluation.status == "INTERNAL_ERROR"
    assert evaluation.score is None
    assert evaluation.passed_tests == 1
    assert evaluation.total_tests == 3
    assert [result.status for result in results] == [
        "PASSED",
        "NOT_RUN",
        "NOT_RUN",
    ]
    assert adaptive.progress_classification is None
    assert adaptive.improvement_streak == 1
    assert state.current_assistance == "MODERATE"
    assert state.consecutive_improvements == 1


def test_infrastructure_failure_is_immediate_predecessor_and_remains_in_history(
    api_database,
) -> None:
    client, TestingSession = api_database

    first = client.post(
        "/api/submissions",
        json={"student_id": 1, "problem_id": 1, "source_code": "score40"},
    ).json()
    failed = client.post(
        "/api/submissions",
        json={"student_id": 1, "problem_id": 1, "source_code": "INTERNAL_FAILURE"},
    )
    later = client.post(
        "/api/submissions",
        json={"student_id": 1, "problem_id": 1, "source_code": "score85"},
    )

    assert failed.status_code == 500
    assert later.status_code == 200
    assert later.json()["progress_classification"] is None
    assert later.json()["selected_assistance_level"] == "LOW"

    history = client.get("/api/students/1/problems/1/history")
    assert history.status_code == 200
    items = history.json()
    assert len(items) == 3
    assert items[0]["submission_id"] == first["submission_id"]
    assert items[1]["evaluation_status"] is None
    assert items[1]["score"] is None
    assert items[1]["progress_classification"] is None
    assert items[1]["selected_assistance_level"] is None
    assert items[2]["progress_classification"] is None

    from app.models.orm import EvaluationResult as OrmEvaluationResult, StudentProblemState

    with TestingSession() as db:
        failed_submission = db.get(Submission, items[1]["submission_id"])
        state = db.query(StudentProblemState).one()
        assert failed_submission is not None
        assert failed_submission.evaluation_result is None
        assert db.query(OrmEvaluationResult).count() == 2
        assert state.current_assistance == "LOW"
        assert state.consecutive_improvements == 0


def test_submission_without_evaluation_is_not_skipped(api_database) -> None:
    client, TestingSession = api_database

    first = client.post(
        "/api/submissions",
        json={"student_id": 1, "problem_id": 1, "source_code": "score40"},
    ).json()

    with TestingSession() as db:
        first_submission = db.get(Submission, first["submission_id"])
        assert first_submission is not None
        pending = Submission(
            student_id=1,
            problem_id=1,
            source_code="PENDING_EVALUATION",
            submitted_at=first_submission.submitted_at + timedelta(seconds=1),
        )
        db.add(pending)
        db.commit()
        pending_id = pending.id

    later = client.post(
        "/api/submissions",
        json={"student_id": 1, "problem_id": 1, "source_code": "score85"},
    )

    assert later.status_code == 200
    assert later.json()["progress_classification"] is None
    assert later.json()["selected_assistance_level"] == "LOW"
    with TestingSession() as db:
        pending_submission = db.get(Submission, pending_id)
        assert pending_submission is not None
        assert pending_submission.evaluation_result is None

        from app.models.orm import StudentProblemState

        state = db.query(StudentProblemState).one()
        assert state.current_assistance == "LOW"
        assert state.consecutive_improvements == 0


def test_null_scored_evaluation_remains_immediate_predecessor(api_database) -> None:
    client, _ = api_database

    first = client.post(
        "/api/submissions",
        json={"student_id": 1, "problem_id": 1, "source_code": "score40"},
    ).json()
    null_score = client.post(
        "/api/submissions",
        json={"student_id": 1, "problem_id": 1, "source_code": "COMPILATION_ERROR"},
    )
    later = client.post(
        "/api/submissions",
        json={"student_id": 1, "problem_id": 1, "source_code": "score85"},
    )

    assert first["progress_classification"] is None
    assert null_score.status_code == 200
    assert null_score.json()["score"] is None
    assert null_score.json()["progress_classification"] is None
    assert later.status_code == 200
    assert later.json()["progress_classification"] is None
    assert later.json()["selected_assistance_level"] == "LOW"


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
