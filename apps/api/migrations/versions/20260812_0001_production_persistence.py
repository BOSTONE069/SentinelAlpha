"""Production persistence baseline with legacy SQLite expansion.

Revision ID: 20260812_0001
Revises: None
Create Date: 2026-08-12
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "20260812_0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _add_legacy_workflow_columns() -> None:
    with op.batch_alter_table("workflow_runs") as batch:
        batch.alter_column("created_at", new_column_name="started_at")
        batch.alter_column("data", new_column_name="legacy_data", nullable=True)
        batch.add_column(sa.Column("portfolio_id", sa.String(64), nullable=True))
        batch.add_column(sa.Column("replay_of", sa.String(64), nullable=True))
        batch.add_column(
            sa.Column("trigger_type", sa.String(40), nullable=False, server_default="manual")
        )
        batch.add_column(
            sa.Column("agent_provider", sa.String(24), nullable=False, server_default="RULES")
        )
        batch.add_column(sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("final_decision", sa.String(30), nullable=True))
        batch.add_column(sa.Column("final_confidence", sa.Numeric(8, 6), nullable=True))
        batch.add_column(sa.Column("error_message", sa.Text(), nullable=True))
        batch.add_column(
            sa.Column("version_id", sa.Integer(), nullable=False, server_default="1")
        )
        batch.create_foreign_key(
            "fk_workflow_runs_portfolio_id_portfolios",
            "portfolios",
            ["portfolio_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch.create_foreign_key(
            "fk_workflow_runs_replay_of_workflow_runs",
            "workflow_runs",
            ["replay_of"],
            ["id"],
            ondelete="SET NULL",
        )
    bind = op.get_bind()
    indexes = {item["name"] for item in sa.inspect(bind).get_indexes("workflow_runs")}
    if "ix_workflow_runs_created_at" in indexes:
        op.drop_index("ix_workflow_runs_created_at", table_name="workflow_runs")
    op.create_index("ix_workflow_runs_started_at", "workflow_runs", ["started_at"])
    op.create_index("ix_workflow_runs_completed_at", "workflow_runs", ["completed_at"])
    op.create_index("ix_workflow_runs_updated_at", "workflow_runs", ["updated_at"])
    op.create_index("ix_workflow_runs_final_decision", "workflow_runs", ["final_decision"])
    op.create_index("ix_workflow_runs_portfolio_id", "workflow_runs", ["portfolio_id"])
    op.create_index("ix_workflow_runs_replay_of", "workflow_runs", ["replay_of"])


def _add_legacy_order_columns() -> None:
    with op.batch_alter_table("execution_orders") as batch:
        batch.alter_column("data", new_column_name="provider_response")
        batch.alter_column("provider_order_id", type_=sa.String(255), nullable=True)
        batch.alter_column("client_order_id", type_=sa.String(255))
        batch.alter_column("symbol", type_=sa.String(20))
        batch.alter_column("side", type_=sa.String(10))
        batch.alter_column("status", type_=sa.String(50))
        batch.alter_column("notional", type_=sa.Numeric(20, 4))
        batch.add_column(
            sa.Column("provider", sa.String(40), nullable=False, server_default="alpaca")
        )
        batch.add_column(
            sa.Column("environment", sa.String(20), nullable=False, server_default="paper")
        )
        batch.add_column(
            sa.Column("order_type", sa.String(30), nullable=False, server_default="market")
        )
        batch.add_column(
            sa.Column("time_in_force", sa.String(20), nullable=False, server_default="day")
        )
        batch.add_column(sa.Column("quantity", sa.Numeric(20, 8), nullable=True))
        batch.add_column(
            sa.Column(
                "execution_mode",
                sa.String(32),
                nullable=False,
                server_default="SIMULATED_PAPER",
            )
        )
        batch.add_column(
            sa.Column("risk_decision", sa.String(30), nullable=False, server_default="APPROVE")
        )
        batch.add_column(sa.Column("filled_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            )
        )
        batch.add_column(
            sa.Column("version_id", sa.Integer(), nullable=False, server_default="1")
        )
        batch.create_foreign_key(
            "fk_execution_orders_workflow_run_id_workflow_runs",
            "workflow_runs",
            ["workflow_run_id"],
            ["id"],
            ondelete="RESTRICT",
        )


def _add_legacy_alert_columns() -> None:
    with op.batch_alter_table("soc_alerts") as batch:
        batch.alter_column("data", new_column_name="details")
        batch.alter_column("rule_id", type_=sa.String(30))
        batch.alter_column("severity", type_=sa.String(20))
        batch.alter_column("status", type_=sa.String(30))
        batch.add_column(
            sa.Column("alert_type", sa.String(80), nullable=False, server_default="legacy")
        )
        batch.add_column(
            sa.Column("title", sa.String(255), nullable=False, server_default="Legacy alert")
        )
        batch.add_column(
            sa.Column("detail", sa.Text(), nullable=False, server_default="Migrated alert")
        )
        batch.add_column(sa.Column("symbol", sa.String(20), nullable=True))
        batch.add_column(
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            )
        )
        batch.add_column(sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(
            sa.Column("version_id", sa.Integer(), nullable=False, server_default="1")
        )
        batch.create_foreign_key(
            "fk_soc_alerts_workflow_run_id_workflow_runs",
            "workflow_runs",
            ["workflow_run_id"],
            ["id"],
            ondelete="CASCADE",
        )
    op.create_index("ix_soc_alerts_alert_type", "soc_alerts", ["alert_type"])
    op.create_index("ix_soc_alerts_symbol", "soc_alerts", ["symbol"])


def _backfill_legacy_columns() -> None:
    bind = op.get_bind()
    now = datetime.now(timezone.utc)
    orders = sa.table(
        "execution_orders",
        sa.column("id", sa.String),
        sa.column("provider_response", sa.JSON),
        sa.column("execution_mode", sa.String),
        sa.column("risk_decision", sa.String),
        sa.column("quantity", sa.Numeric),
        sa.column("filled_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )
    for row in bind.execute(sa.select(orders.c.id, orders.c.provider_response)).mappings():
        payload = row["provider_response"] or {}
        filled_at = payload.get("filled_at")
        bind.execute(
            orders.update()
            .where(orders.c.id == row["id"])
            .values(
                execution_mode=payload.get("execution_mode", "SIMULATED_PAPER"),
                risk_decision=payload.get("risk_decision", "APPROVE"),
                quantity=payload.get("quantity"),
                filled_at=(
                    datetime.fromisoformat(filled_at.replace("Z", "+00:00"))
                    if isinstance(filled_at, str)
                    else filled_at
                ),
                updated_at=now,
            )
        )

    alerts = sa.table(
        "soc_alerts",
        sa.column("id", sa.String),
        sa.column("details", sa.JSON),
        sa.column("alert_type", sa.String),
        sa.column("title", sa.String),
        sa.column("detail", sa.Text),
        sa.column("symbol", sa.String),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )
    for row in bind.execute(sa.select(alerts.c.id, alerts.c.details)).mappings():
        payload = row["details"] or {}
        bind.execute(
            alerts.update()
            .where(alerts.c.id == row["id"])
            .values(
                alert_type=payload.get("alert_type", "legacy"),
                title=payload.get("title", "Legacy alert"),
                detail=payload.get("detail", "Migrated alert"),
                symbol=payload.get("symbol"),
                updated_at=now,
            )
        )


def upgrade() -> None:
    # New installations use a frozen schema snapshot so this historical
    # migration cannot change when the application's ORM models evolve.
    # Existing three-table SQLite installs still need the compatibility path
    # below before startup normalizes their JSON documents.
    bind = op.get_bind()
    existing = set(sa.inspect(bind).get_table_names())
    application_tables = existing - {"alembic_version"}
    if not application_tables:
        from migrations.schema_20260812 import create_schema

        create_schema()
        return

    from app.db import Base

    legacy = "workflow_runs" in existing and "legacy_data" not in {
        column["name"] for column in sa.inspect(bind).get_columns("workflow_runs")
    }

    Base.metadata.create_all(bind=bind, checkfirst=True)
    if legacy:
        _add_legacy_workflow_columns()
        _add_legacy_order_columns()
        _add_legacy_alert_columns()
        _backfill_legacy_columns()


def downgrade() -> None:
    from migrations.schema_20260812 import drop_schema

    drop_schema()
