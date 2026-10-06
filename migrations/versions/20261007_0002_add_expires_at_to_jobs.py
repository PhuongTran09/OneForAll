"""add expires_at to jobs table and expired status

Revision ID: 20261007_0002
Revises: 20261006_0001
Create Date: 2026-10-07
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261007_0002"
down_revision: str | None = "20261006_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("jobs", sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_jobs_expires_at", "jobs", ["expires_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_jobs_expires_at", table_name="jobs")
    op.drop_column("jobs", "expires_at")
