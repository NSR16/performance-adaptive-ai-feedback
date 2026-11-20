from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import desc, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import Settings, settings
from app.models.orm import (
    AdaptiveDecision,
    EvaluationResult as OrmEvaluationResult,
    Feedback,
    Problem,
    Student,
    StudentProblemState,
    Submission,
    TestCase,
    TestCaseResult as OrmTestCaseResult,
)
from app.services.adaptive import AssistanceLevel, select_assistance
from app.services.evaluation import EvaluationEngine, EvaluationResult, TestCaseInput
from app.services.feedback import OllamaFeedbackGenerator
from app.services.progress import ProgressAttempt, analyze_progress


class SubmissionWorkflowError(Exception):
    def __init__(self, message: str, status_code: int = 500) -> None:
        super().__init__(message)
        self.status_code = status_code


class SubmissionWorkflow:
    def __init__(
        self,
        db: Session,
        engine: EvaluationEngine | None = None,
        feedback_generator: OllamaFeedbackGenerator | None = None,
        config: Settings | None = None,
    ) -> None:
        self.db = db
        self.engine = engine or EvaluationEngine()
        self.feedback_generator = feedback_generator or OllamaFeedbackGenerator(config=config)
        self.config = config or settings

    async def execute(
        self,
        student_id: int,
        problem_id: int,
        source_code: str,
    ) -> dict[str, object]:
        try:
            student = self.db.get(Student, student_id)
            if student is None:
                raise SubmissionWorkflowError("Student not found.", 404)
            problem = self.db.get(Problem, problem_id)
            if problem is None:
                raise SubmissionWorkflowError("Problem not found.", 404)

            test_cases = list(
                self.db.execute(
                    select(TestCase)
                    .where(TestCase.problem_id == problem_id)
                    .order_by(TestCase.sequence_order, TestCase.id)
                ).scalars()
            )
            if not test_cases:
                raise SubmissionWorkflowError(
                    "Problem has no test cases.",
                    422,
                )

            previous = self._get_previous_submission(student_id, problem_id)
            submitted_at = datetime.now(timezone.utc)
            if previous is not None:
                previous_at = _aware(previous.submitted_at)
                if submitted_at <= previous_at:
                    submitted_at = previous_at + timedelta(microseconds=1)

            submission = Submission(
                student_id=student_id,
                problem_id=problem_id,
                source_code=source_code,
                submitted_at=submitted_at,
            )
            self.db.add(submission)
            self.db.commit()
            self.db.refresh(submission)
        except SubmissionWorkflowError:
            self.db.rollback()
            raise
        except SQLAlchemyError as exc:
            self.db.rollback()
            raise SubmissionWorkflowError("Database operation failed.") from exc

        evaluation_cases = [
            TestCaseInput(
                test_case_id=test_case.id,
                input_data=test_case.input_data,
                expected_output=test_case.expected_output,
                is_hidden=test_case.is_hidden,
                sequence_order=test_case.sequence_order,
            )
            for test_case in test_cases
        ]
        sequence_by_test_case_id = {
            test_case.id: test_case.sequence_order
            for test_case in test_cases
        }

        try:
            import asyncio

            evaluation = await asyncio.to_thread(
                self.engine.evaluate,
                source_code,
                evaluation_cases,
            )
        except Exception as exc:
            raise SubmissionWorkflowError(
                f"Evaluation infrastructure failed: {type(exc).__name__}."
            ) from exc

        previous_attempt = (
            _to_progress_attempt(previous)
            if previous is not None and previous.evaluation_result is not None
            else None
        )
        current_attempt = ProgressAttempt(
            student_id=student_id,
            problem_id=problem_id,
            submitted_at=_aware(submission.submitted_at),
            evaluation=evaluation,
        )
        progress = analyze_progress(previous_attempt, current_attempt)

        try:
            state = self.db.execute(
                select(StudentProblemState)
                .where(
                    StudentProblemState.student_id == student_id,
                    StudentProblemState.problem_id == problem_id,
                )
                .with_for_update()
            ).scalar_one_or_none()
            if state is None:
                state = StudentProblemState(
                    student_id=student_id,
                    problem_id=problem_id,
                    current_assistance=AssistanceLevel.LOW.value,
                    consecutive_improvements=0,
                )
                self.db.add(state)
                self.db.flush()

            previous_assistance = AssistanceLevel(state.current_assistance)
            previous_streak = state.consecutive_improvements
            decision = select_assistance(
                progress.classification,
                previous_assistance=previous_assistance,
                previous_improvement_streak=previous_streak,
            )

            orm_evaluation = OrmEvaluationResult(
                submission_id=submission.id,
                status=evaluation.status,
                passed_tests=evaluation.passed_tests,
                total_tests=evaluation.total_tests,
                score=evaluation.score,
                execution_time_ms=evaluation.execution_time_ms,
                compilation_error=evaluation.compilation_error,
                runtime_error=evaluation.runtime_error,
            )
            self.db.add(orm_evaluation)
            self.db.flush()

            for result in evaluation.test_case_results:
                self.db.add(
                    OrmTestCaseResult(
                        evaluation_id=orm_evaluation.id,
                        test_case_id=result.test_case_id,
                        status=result.status,
                        actual_output=result.actual_output,
                        execution_time_ms=result.execution_time_ms,
                        error_message=result.error_message,
                    )
                )

            state.current_assistance = decision.selected_assistance.value
            state.consecutive_improvements = decision.updated_improvement_streak

            adaptive = AdaptiveDecision(
                submission_id=submission.id,
                student_problem_state_id=state.id,
                progress_classification=(
                    progress.classification.value
                    if progress.classification is not None
                    else None
                ),
                previous_assistance=decision.previous_assistance.value,
                selected_assistance=decision.selected_assistance.value,
                improvement_streak=decision.updated_improvement_streak,
            )
            self.db.add(adaptive)
            self.db.flush()

            feedback = Feedback(
                submission_id=submission.id,
                adaptive_decision_id=adaptive.id,
                feedback_text=None,
                generation_status="PENDING",
                model_name=self.config.OLLAMA_MODEL,
                error_message=None,
            )
            self.db.add(feedback)
            self.db.commit()
            self.db.refresh(submission)
        except SQLAlchemyError as exc:
            self.db.rollback()
            raise SubmissionWorkflowError("Database operation failed.") from exc

        generation = await self.feedback_generator.generate_feedback(
            problem_description=problem.description,
            source_code=source_code,
            evaluation_result=evaluation,
            assistance_level=decision.selected_assistance,
        )

        try:
            feedback_record = self.db.execute(
                select(Feedback).where(Feedback.submission_id == submission.id)
            ).scalar_one()
            feedback_record.feedback_text = generation.feedback_text
            feedback_record.model_name = generation.model_name
            feedback_record.generation_status = generation.generation_status
            feedback_record.error_message = generation.error_message
            self.db.commit()
            self.db.refresh(feedback_record)
        except SQLAlchemyError as exc:
            self.db.rollback()
            raise SubmissionWorkflowError("Database operation failed.") from exc

        return {
            "submission_id": submission.id,
            "evaluation_status": evaluation.status,
            "passed_tests": evaluation.passed_tests,
            "total_tests": evaluation.total_tests,
            "score": evaluation.score,
            "progress_classification": (
                progress.classification.value
                if progress.classification is not None
                else None
            ),
            "selected_assistance_level": decision.selected_assistance.value,
            "feedback_text": feedback_record.feedback_text,
            "generation_status": feedback_record.generation_status,
            "model_name": feedback_record.model_name,
            "error_message": feedback_record.error_message,
            "test_case_results": [
                {
                    "sequence_order": sequence_by_test_case_id[result.test_case_id],
                    "status": result.status,
                    "execution_time_ms": result.execution_time_ms,
                }
                for result in sorted(
                    evaluation.test_case_results,
                    key=lambda item: sequence_by_test_case_id[item.test_case_id],
                )
            ],
        }

    def _get_previous_submission(
        self,
        student_id: int,
        problem_id: int,
    ) -> Submission | None:
        return self.db.execute(
            select(Submission)
            .where(
                Submission.student_id == student_id,
                Submission.problem_id == problem_id,
            )
            .order_by(desc(Submission.submitted_at), desc(Submission.id))
            .limit(1)
        ).scalar_one_or_none()


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def _to_progress_attempt(submission: Submission) -> ProgressAttempt:
    evaluation = submission.evaluation_result
    if evaluation is None:
        raise SubmissionWorkflowError("Previous submission has no evaluation.")

    dataclass_evaluation = EvaluationResult(
        status=evaluation.status,
        passed_tests=evaluation.passed_tests,
        total_tests=evaluation.total_tests,
        score=evaluation.score,
        execution_time_ms=evaluation.execution_time_ms,
        compilation_error=evaluation.compilation_error,
        runtime_error=evaluation.runtime_error,
        test_case_results=[
            _test_case_to_dataclass(result)
            for result in evaluation.test_case_results
        ],
        internal_error=None,
    )
    return ProgressAttempt(
        student_id=submission.student_id,
        problem_id=submission.problem_id,
        submitted_at=_aware(submission.submitted_at),
        evaluation=dataclass_evaluation,
    )


def _test_case_to_dataclass(result: OrmTestCaseResult):
    from app.services.evaluation.schemas import TestCaseResult

    return TestCaseResult(
        test_case_id=result.test_case_id,
        status=result.status,
        actual_output=result.actual_output,
        execution_time_ms=result.execution_time_ms,
        error_message=result.error_message,
    )
