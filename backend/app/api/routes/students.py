from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.orm import (
    AdaptiveDecision,
    EvaluationResult,
    Feedback,
    Problem,
    Student,
    StudentProblemState,
    Submission,
    TestCaseResult,
)
from app.schemas.submissions import (
    HistoryItem,
    HistoryResetResponse,
    StudentSummary,
)

router = APIRouter(tags=["students"])


@router.get("/api/students", response_model=list[StudentSummary])
def list_students(db: Session = Depends(get_db)) -> list[StudentSummary]:
    students = db.execute(select(Student).order_by(Student.id.asc())).scalars().all()
    return [
        StudentSummary(id=student.id, display_name=student.display_name)
        for student in students
    ]


@router.get(
    "/api/students/{student_id}/problems/{problem_id}/history",
    response_model=list[HistoryItem],
)
def get_history(
    student_id: int,
    problem_id: int,
    db: Session = Depends(get_db),
) -> list[HistoryItem]:
    if student_id <= 0 or problem_id <= 0:
        raise HTTPException(status_code=422, detail="student_id and problem_id must be positive.")
    if db.get(Student, student_id) is None:
        raise HTTPException(status_code=404, detail="Student not found.")
    if db.get(Problem, problem_id) is None:
        raise HTTPException(status_code=404, detail="Problem not found.")

    submissions = db.execute(
        select(Submission)
        .where(
            Submission.student_id == student_id,
            Submission.problem_id == problem_id,
        )
        .order_by(Submission.submitted_at.asc(), Submission.id.asc())
    ).scalars().all()

    return [
        HistoryItem(
            submission_id=submission.id,
            submitted_at=submission.submitted_at,
            evaluation_status=(
                submission.evaluation_result.status
                if submission.evaluation_result
                else None
            ),
            passed_tests=(
                submission.evaluation_result.passed_tests
                if submission.evaluation_result
                else None
            ),
            total_tests=(
                submission.evaluation_result.total_tests
                if submission.evaluation_result
                else None
            ),
            score=(
                submission.evaluation_result.score
                if submission.evaluation_result
                else None
            ),
            progress_classification=(
                submission.adaptive_decision.progress_classification
                if submission.adaptive_decision
                else None
            ),
            selected_assistance_level=(
                submission.adaptive_decision.selected_assistance
                if submission.adaptive_decision
                else None
            ),
        )
        for submission in submissions
    ]


@router.delete(
    "/api/students/{student_id}/problems/{problem_id}/history",
    response_model=HistoryResetResponse,
)
def reset_history(
    student_id: int,
    problem_id: int,
    db: Session = Depends(get_db),
) -> HistoryResetResponse:
    if student_id <= 0 or problem_id <= 0:
        raise HTTPException(status_code=422, detail="student_id and problem_id must be positive.")
    if db.get(Student, student_id) is None:
        raise HTTPException(status_code=404, detail="Student not found.")
    if db.get(Problem, problem_id) is None:
        raise HTTPException(status_code=404, detail="Problem not found.")

    submission_ids = list(
        db.execute(
            select(Submission.id).where(
                Submission.student_id == student_id,
                Submission.problem_id == problem_id,
            )
        ).scalars()
    )
    deleted_submissions = len(submission_ids)

    if submission_ids:
        evaluation_ids = list(
            db.execute(
                select(EvaluationResult.id).where(
                    EvaluationResult.submission_id.in_(submission_ids)
                )
            ).scalars()
        )
        db.execute(
            delete(Feedback).where(Feedback.submission_id.in_(submission_ids))
        )
        db.execute(
            delete(AdaptiveDecision).where(
                AdaptiveDecision.submission_id.in_(submission_ids)
            )
        )
        if evaluation_ids:
            db.execute(
                delete(TestCaseResult).where(
                    TestCaseResult.evaluation_id.in_(evaluation_ids)
                )
            )
            db.execute(
                delete(EvaluationResult).where(
                    EvaluationResult.submission_id.in_(submission_ids)
                )
            )
        db.execute(
            delete(Submission).where(
                Submission.student_id == student_id,
                Submission.problem_id == problem_id,
            )
        )

    db.execute(
        delete(StudentProblemState).where(
            StudentProblemState.student_id == student_id,
            StudentProblemState.problem_id == problem_id,
        )
    )
    db.commit()

    return HistoryResetResponse(
        student_id=student_id,
        problem_id=problem_id,
        deleted_submissions=deleted_submissions,
    )
