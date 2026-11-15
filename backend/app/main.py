from fastapi import FastAPI

app = FastAPI(
    title="Performance-Adaptive AI Feedback",
    description="Backend for evaluating adaptive AI feedback in independent programming problem-solving.",
)


@app.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok"}
