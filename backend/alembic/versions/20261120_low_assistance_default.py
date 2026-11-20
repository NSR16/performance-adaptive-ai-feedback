"""Use LOW as the default for new student-problem adaptive states.

Revision ID: 20261120_low_assistance_default
Revises: 20261116_initial_schema
Create Date: 2026-11-20 10:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "20261120_low_assistance_default"
down_revision = "20261116_initial_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "student_problem_states",
        "current_assistance",
        existing_type=sa.String(length=10),
        existing_nullable=False,
        server_default="LOW",
    )


def downgrade() -> None:
    op.alter_column(
        "student_problem_states",
        "current_assistance",
        existing_type=sa.String(length=10),
        existing_nullable=False,
        server_default="MODERATE",
    )
