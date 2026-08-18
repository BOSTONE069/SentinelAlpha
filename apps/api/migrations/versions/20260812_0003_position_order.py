"""Preserve source ordering for normalized position snapshots.

Revision ID: 20260812_0003
Revises: 20260812_0002
Create Date: 2026-08-12
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "20260812_0003"
down_revision: Union[str, None] = "20260812_0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    columns = {item["name"] for item in sa.inspect(bind).get_columns("positions")}
    if "ordinal" not in columns:
        with op.batch_alter_table("positions") as batch:
            batch.add_column(
                sa.Column("ordinal", sa.Integer(), nullable=False, server_default="0")
            )
    else:
        return

    positions = sa.table(
        "positions",
        sa.column("id", sa.String),
        sa.column("workflow_run_id", sa.String),
        sa.column("symbol", sa.String),
        sa.column("ordinal", sa.Integer),
    )
    rows = bind.execute(
        sa.select(positions.c.id, positions.c.workflow_run_id, positions.c.symbol)
        .order_by(positions.c.workflow_run_id, positions.c.symbol)
    ).mappings()
    current_run = None
    ordinal = 0
    for row in rows:
        if row["workflow_run_id"] != current_run:
            current_run = row["workflow_run_id"]
            ordinal = 0
        bind.execute(
            positions.update()
            .where(positions.c.id == row["id"])
            .values(ordinal=ordinal)
        )
        ordinal += 1


def downgrade() -> None:
    with op.batch_alter_table("positions") as batch:
        batch.drop_column("ordinal")
