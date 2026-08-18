"""Align legacy constraints, indexes, and JSON null semantics.

Revision ID: 20260812_0002
Revises: 20260812_0001
Create Date: 2026-08-12
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "20260812_0002"
down_revision: Union[str, None] = "20260812_0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_name)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


def upgrade() -> None:
    bind = op.get_bind()
    # Recreate on SQLite so anonymous constraints inherited from the original
    # create_all schema receive deterministic Alembic names.
    recreate = "always" if bind.dialect.name == "sqlite" else "auto"
    with op.batch_alter_table(
        "workflow_runs", recreate=recreate, naming_convention=NAMING_CONVENTION
    ) as batch:
        batch.alter_column(
            "symbol", existing_type=sa.String(12), type_=sa.String(20), existing_nullable=False
        )
        batch.alter_column(
            "status", existing_type=sa.String(32), type_=sa.String(40), existing_nullable=False
        )

    with op.batch_alter_table(
        "execution_orders", recreate=recreate, naming_convention=NAMING_CONVENTION
    ):
        pass

    indexes = {item["name"] for item in sa.inspect(bind).get_indexes("execution_orders")}
    if "ix_execution_orders_filled_at" not in indexes:
        op.create_index(
            "ix_execution_orders_filled_at", "execution_orders", ["filled_at"]
        )

    if bind.dialect.name == "postgresql":
        op.execute(
            "UPDATE workflow_runs SET legacy_data = NULL "
            "WHERE jsonb_typeof(legacy_data) = 'null'"
        )
    elif bind.dialect.name == "sqlite":
        op.execute(
            "UPDATE workflow_runs SET legacy_data = NULL "
            "WHERE legacy_data = 'null'"
        )


def downgrade() -> None:
    with op.batch_alter_table("workflow_runs") as batch:
        batch.alter_column(
            "symbol", existing_type=sa.String(20), type_=sa.String(12), existing_nullable=False
        )
        batch.alter_column(
            "status", existing_type=sa.String(40), type_=sa.String(32), existing_nullable=False
        )
    indexes = {item["name"] for item in sa.inspect(op.get_bind()).get_indexes("execution_orders")}
    if "ix_execution_orders_filled_at" in indexes:
        op.drop_index("ix_execution_orders_filled_at", table_name="execution_orders")
