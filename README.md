# Performance-Adaptive AI Feedback for Independent Programming Problem-Solving: A Comparative Evaluation

## Research objective

Evaluate how performance-adaptive AI feedback affects learners' independent programming problem-solving.

## Project description

This project will compare feedback approaches using the CodeWorkout Spring 2019 dataset. Historical data analysis is kept independent from the application backend.

## Technology stack

- **Backend:** Python 3.13, FastAPI, SQLAlchemy 2.0, Alembic, Pydantic, Pandas, pytest, HTTPX
- **Database:** PostgreSQL 17
- **Frontend:** React, TypeScript, Vite; Monaco Editor is planned for the future code editor
- **Evaluation:** Java
- **Version control:** Git

## High-level architecture

- `backend/` contains the FastAPI application and its service and test organization.
- `frontend/` contains the React + TypeScript web application.
- `analysis/` contains standalone scripts and notebooks for historical dataset analysis.
- `dataset/` holds the existing dataset and is excluded from Git.

## Current development status

The initial repository structure and database foundation are in place. The backend includes the Java evaluation service; progress/adaptive research algorithms, authentication, public evaluation APIs, and LLM integration remain future work.

## Database setup

1. Create a PostgreSQL 17 database and role for the project.
2. Copy `backend/.env.example` to a local `.env` file and set `DATABASE_URL` to your PostgreSQL connection string.
3. In `backend/`, create and activate a Python virtual environment, then install dependencies:
   - `python -m venv .venv`
   - `.venv\Scripts\Activate.ps1` (PowerShell) or `.venv/bin/activate` (POSIX)
   - `pip install -r requirements.txt`
4. Run database migrations from the `backend/` directory:
   - `alembic upgrade head`
5. Run the database foundation tests:
   - `pytest tests/test_database_foundation.py`

The project intentionally keeps the dataset independent from the application and does not commit an actual `.env` file.

## Java evaluation

Install a Java JDK with both `javac` and `java` available on `PATH`. Verify the installation with `javac -version` and `java -version`. The compiler, runtime, class name, compilation timeout, and per-test timeout can be configured through `JAVA_COMPILER`, `JAVA_RUNTIME`, `JAVA_CLASS_NAME`, `JAVA_COMPILATION_TIMEOUT_SECONDS`, and `JAVA_EXECUTION_TIMEOUT_SECONDS`; the default class name is `Main` and the default per-test timeout is 2 seconds.

Run the evaluation tests from `backend/` with `pytest tests/test_evaluation.py`. The service compiles each submission once and launches a fresh process for every test case. This local academic prototype does not securely isolate arbitrary untrusted code; do not expose it as a public code-execution service without an appropriate sandbox.
