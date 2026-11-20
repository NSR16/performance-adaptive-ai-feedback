from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.orm import Submission
from app.schemas.submissions import (
    SubmissionCreate,
    SubmissionDetail,
    SubmissionResponse,
    SubmissionTestCaseResult,
)
from app.services.submissions import SubmissionWorkflow, SubmissionWorkflowError

router = APIRouter(tags=["submissions"])


def get_submission_workflow(db: Session = Depends(get_db)) -> SubmissionWorkflow:
    return SubmissionWorkflow(db=db)


@router.post("/api/submissions", response_model=SubmissionResponse)
async def create_submission(
    request: SubmissionCreate,
    workflow: SubmissionWorkflow = Depends(get_submission_workflow),
) -> SubmissionResponse:
    try:
        result = await workflow.execute(
            student_id=request.student_id,
            problem_id=request.problem_id,
            source_code=request.source_code,
        )
        return SubmissionResponse(**result)
    except SubmissionWorkflowError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@router.get("/api/submissions/{submission_id}", response_model=SubmissionDetail)
def get_submission(
    submission_id: int,
    db: Session = Depends(get_db),
) -> SubmissionDetail:
    if submission_id <= 0:
        raise HTTPException(status_code=422, detail="submission_id must be positive.")
    submission = db.get(Submission, submission_id)
    if submission is None:
        raise HTTPException(status_code=404, detail="Submission not found.")

    evaluation = submission.evaluation_result
    adaptive = submission.adaptive_decision
    feedback = submission.feedback
    test_case_results = (
        [
            SubmissionTestCaseResult(
                sequence_order=result.test_case.sequence_order,
                status=result.status,
                execution_time_ms=result.execution_time_ms,
            )
            for result in sorted(
                evaluation.test_case_results,
                key=lambda item: (
                    item.test_case.sequence_order,
                    item.test_case_id,
                ),
            )
        ]
        if evaluation
        else []
    )
    return SubmissionDetail(
        submission_id=submission.id,
        student_id=submission.student_id,
        problem_id=submission.problem_id,
        submitted_at=submission.submitted_at,
        source_code=submission.source_code,
        evaluation_status=evaluation.status if evaluation else None,
        passed_tests=evaluation.passed_tests if evaluation else None,
        total_tests=evaluation.total_tests if evaluation else None,
        score=evaluation.score if evaluation else None,
        progress_classification=adaptive.progress_classification if adaptive else None,
        selected_assistance_level=adaptive.selected_assistance if adaptive else None,
        improvement_streak=adaptive.improvement_streak if adaptive else None,
        feedback_text=feedback.feedback_text if feedback else None,
        feedback_generation_status=feedback.generation_status if feedback else None,
        feedback_error_message=feedback.error_message if feedback else None,
        model_name=feedback.model_name if feedback else None,
        test_case_results=test_case_results,
    )
