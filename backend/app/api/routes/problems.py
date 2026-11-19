from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.orm import Problem
from app.schemas.submissions import ProblemDetail, ProblemSummary, PublicTestCase

router = APIRouter(tags=["problems"])


@router.get("/api/problems", response_model=list[ProblemSummary])
def list_problems(db: Session = Depends(get_db)) -> list[ProblemSummary]:
    problems = db.query(Problem).order_by(Problem.id).all()
    return [
        ProblemSummary(id=problem.id, title=problem.title, difficulty=problem.difficulty)
        for problem in problems
    ]


@router.get("/api/problems/{problem_id}", response_model=ProblemDetail)
def get_problem(problem_id: int, db: Session = Depends(get_db)) -> ProblemDetail:
    if problem_id <= 0:
        raise HTTPException(status_code=422, detail="problem_id must be positive.")
    problem = db.get(Problem, problem_id)
    if problem is None:
        raise HTTPException(status_code=404, detail="Problem not found.")

    public_cases = [
        PublicTestCase(
            id=test_case.id,
            input_data=test_case.input_data,
            expected_output=test_case.expected_output,
            sequence_order=test_case.sequence_order,
        )
        for test_case in sorted(
            (test_case for test_case in problem.test_cases if not test_case.is_hidden),
            key=lambda test_case: (test_case.sequence_order, test_case.id),
        )
    ]
    hidden_count = sum(test_case.is_hidden for test_case in problem.test_cases)
    return ProblemDetail(
        id=problem.id,
        title=problem.title,
        description=problem.description,
        difficulty=problem.difficulty,
        starter_code=problem.starter_code,
        public_test_cases=public_cases,
        hidden_test_case_count=hidden_count,
    )
