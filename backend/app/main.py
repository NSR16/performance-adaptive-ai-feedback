from fastapi import FastAPI
from app.api.routes.problems import router as problems_router
from app.api.routes.submissions import router as submissions_router
from app.api.routes.students import router as students_router

app = FastAPI(
    title="Performance-Adaptive AI Feedback",
    description="Backend for evaluating adaptive AI feedback in independent programming problem-solving.",
)

app.include_router(problems_router)
app.include_router(submissions_router)
app.include_router(students_router)


@app.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok"}
