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

Initial repository structure and development environments are being established. The backend currently provides a health check; research algorithms, database models and migrations, Java evaluation, authentication, and LLM integration are not implemented.
