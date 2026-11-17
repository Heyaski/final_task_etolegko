"""settings and activity log

Revision ID: 001_initial
Revises:
Create Date: 2026-11-17
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "app_settings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("keitaro_base_url", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("keitaro_api_key", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_table(
        "activity_log",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("campaign_id", sa.Integer(), nullable=True),
        sa.Column("detail", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("activity_log")
    op.drop_table("app_settings")
