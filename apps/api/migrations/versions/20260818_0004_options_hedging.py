"""Add protective-put workflow and execution metadata.

Revision ID: 20260818_0004
Revises: 20260812_0003
Create Date: 2026-08-18
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "20260818_0004"
down_revision: Union[str, None] = "20260812_0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("workflow_runs") as batch:
        batch.add_column(
            sa.Column(
                "strategy",
                sa.String(length=32),
                nullable=False,
                server_default="EQUITY",
            )
        )
        batch.add_column(sa.Column("hedge_plan", sa.JSON(), nullable=True))

    with op.batch_alter_table("portfolio_snapshots") as batch:
        batch.add_column(sa.Column("options_buying_power", sa.Numeric(20, 4)))
        batch.add_column(
            sa.Column(
                "options_approved_level",
                sa.Integer(),
                nullable=False,
                server_default="0",
            )
        )
        batch.add_column(
            sa.Column(
                "options_trading_level",
                sa.Integer(),
                nullable=False,
                server_default="0",
            )
        )

    with op.batch_alter_table("trade_proposals") as batch:
        batch.alter_column(
            "symbol",
            existing_type=sa.String(length=20),
            type_=sa.String(length=32),
            existing_nullable=False,
        )
        batch.add_column(
            sa.Column(
                "instrument_type",
                sa.String(length=20),
                nullable=False,
                server_default="EQUITY",
            )
        )
        batch.add_column(sa.Column("underlying_symbol", sa.String(length=20)))
        batch.add_column(sa.Column("position_intent", sa.String(length=30)))
        batch.create_index(
            "ix_trade_proposals_underlying_symbol", ["underlying_symbol"]
        )

    with op.batch_alter_table("execution_orders") as batch:
        batch.alter_column(
            "symbol",
            existing_type=sa.String(length=20),
            type_=sa.String(length=32),
            existing_nullable=False,
        )
        batch.add_column(
            sa.Column(
                "instrument_type",
                sa.String(length=20),
                nullable=False,
                server_default="EQUITY",
            )
        )
        batch.add_column(sa.Column("underlying_symbol", sa.String(length=20)))
        batch.add_column(sa.Column("limit_price", sa.Numeric(18, 6)))
        batch.add_column(sa.Column("position_intent", sa.String(length=30)))
        batch.add_column(
            sa.Column(
                "execution_interface",
                sa.String(length=32),
                nullable=False,
                server_default="ALPACA_SDK",
            )
        )
        batch.create_index(
            "ix_execution_orders_underlying_symbol", ["underlying_symbol"]
        )


def downgrade() -> None:
    with op.batch_alter_table("execution_orders") as batch:
        batch.drop_index("ix_execution_orders_underlying_symbol")
        batch.drop_column("execution_interface")
        batch.drop_column("position_intent")
        batch.drop_column("limit_price")
        batch.drop_column("underlying_symbol")
        batch.drop_column("instrument_type")
        batch.alter_column(
            "symbol",
            existing_type=sa.String(length=32),
            type_=sa.String(length=20),
            existing_nullable=False,
        )

    with op.batch_alter_table("trade_proposals") as batch:
        batch.drop_index("ix_trade_proposals_underlying_symbol")
        batch.drop_column("position_intent")
        batch.drop_column("underlying_symbol")
        batch.drop_column("instrument_type")
        batch.alter_column(
            "symbol",
            existing_type=sa.String(length=32),
            type_=sa.String(length=20),
            existing_nullable=False,
        )

    with op.batch_alter_table("portfolio_snapshots") as batch:
        batch.drop_column("options_trading_level")
        batch.drop_column("options_approved_level")
        batch.drop_column("options_buying_power")

    with op.batch_alter_table("workflow_runs") as batch:
        batch.drop_column("hedge_plan")
        batch.drop_column("strategy")
