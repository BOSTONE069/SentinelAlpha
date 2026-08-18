from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Iterator
from uuid import UUID, uuid5

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    MetaData,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    create_engine,
    delete,
    event,
    func,
    select,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from .config import get_settings
from .coordination import CoordinationBackend, get_coordination


NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_name)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}
JSON_DOCUMENT = JSON(none_as_null=True).with_variant(
    JSONB(none_as_null=True), "postgresql"
)
ID_NAMESPACE = UUID("778a42bb-9615-4550-9167-a805da88b7b1")
SYSTEM_USER_ID = "00000000-0000-0000-0000-000000000001"
SYSTEM_PORTFOLIO_ID = "00000000-0000-0000-0000-000000000002"


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class UserRecord(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    email: Mapped[str | None] = mapped_column(String(255), unique=True)
    display_name: Mapped[str | None] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class PortfolioRecord(Base):
    __tablename__ = "portfolios"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    name: Mapped[str] = mapped_column(String(120))
    provider: Mapped[str] = mapped_column(String(50), default="alpaca")
    environment: Mapped[str] = mapped_column(String(20), default="paper")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class WorkflowRecord(Base):
    __tablename__ = "workflow_runs"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    portfolio_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("portfolios.id", ondelete="SET NULL"), index=True
    )
    replay_of: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("workflow_runs.id", ondelete="SET NULL"), index=True
    )
    symbol: Mapped[str] = mapped_column(String(20), index=True)
    trigger_type: Mapped[str] = mapped_column(String(40), default="manual")
    status: Mapped[str] = mapped_column(String(40), index=True)
    mode: Mapped[str] = mapped_column(String(16))
    scenario: Mapped[str] = mapped_column(String(48))
    agent_provider: Mapped[str] = mapped_column(String(24), default="RULES")
    strategy: Mapped[str] = mapped_column(String(32), default="EQUITY")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    final_decision: Mapped[str | None] = mapped_column(String(30), index=True)
    final_confidence: Mapped[Decimal | None] = mapped_column(Numeric(8, 6))
    error_message: Mapped[str | None] = mapped_column(Text)
    version_id: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    # Transitional read-only fallback for rows created by the pre-Alembic schema.
    legacy_data: Mapped[dict | None] = mapped_column(JSON_DOCUMENT)
    hedge_plan: Mapped[dict | None] = mapped_column(JSON_DOCUMENT)

    __mapper_args__ = {"version_id_col": version_id}


class MarketSnapshotRecord(Base):
    __tablename__ = "market_snapshots"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    workflow_run_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("workflow_runs.id", ondelete="CASCADE"), unique=True, index=True
    )
    symbol: Mapped[str] = mapped_column(String(20), index=True)
    price: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    change_pct: Mapped[Decimal] = mapped_column(Numeric(12, 8))
    snapshot_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    source: Mapped[str] = mapped_column(String(32))
    features: Mapped[dict] = mapped_column(JSON_DOCUMENT)
    bars: Mapped[list] = mapped_column(JSON_DOCUMENT)


class NewsItemRecord(Base):
    __tablename__ = "news_items"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    workflow_run_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("workflow_runs.id", ondelete="CASCADE"), index=True
    )
    external_id: Mapped[str | None] = mapped_column(String(255), index=True)
    symbol: Mapped[str] = mapped_column(String(20), index=True)
    headline: Mapped[str] = mapped_column(Text)
    summary: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(255))
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    sentiment: Mapped[Decimal] = mapped_column(Numeric(8, 6))
    relevance: Mapped[Decimal] = mapped_column(Numeric(8, 6))
    corroborated: Mapped[bool] = mapped_column(Boolean)
    duplicate_group: Mapped[str | None] = mapped_column(String(255))
    information_risk: Mapped[list] = mapped_column(JSON_DOCUMENT)
    metadata_json: Mapped[dict] = mapped_column("metadata", JSON_DOCUMENT)


class PortfolioSnapshotRecord(Base):
    __tablename__ = "portfolio_snapshots"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    workflow_run_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("workflow_runs.id", ondelete="CASCADE"), unique=True, index=True
    )
    account_id: Mapped[str] = mapped_column(String(128), index=True)
    account_status: Mapped[str] = mapped_column(String(40))
    currency: Mapped[str] = mapped_column(String(8))
    equity: Mapped[Decimal] = mapped_column(Numeric(20, 4))
    cash: Mapped[Decimal] = mapped_column(Numeric(20, 4))
    buying_power: Mapped[Decimal] = mapped_column(Numeric(20, 4))
    options_buying_power: Mapped[Decimal | None] = mapped_column(Numeric(20, 4))
    options_approved_level: Mapped[int] = mapped_column(Integer, default=0)
    options_trading_level: Mapped[int] = mapped_column(Integer, default=0)
    day_pl: Mapped[Decimal] = mapped_column(Numeric(20, 4))
    day_pl_pct: Mapped[Decimal] = mapped_column(Numeric(12, 8))
    portfolio_drawdown_pct: Mapped[Decimal] = mapped_column(Numeric(12, 8))
    trades_today: Mapped[int] = mapped_column(Integer)
    open_orders: Mapped[list] = mapped_column(JSON_DOCUMENT)
    source: Mapped[str] = mapped_column(String(32))
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class PositionRecord(Base):
    __tablename__ = "positions"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    workflow_run_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("workflow_runs.id", ondelete="CASCADE"), index=True
    )
    portfolio_snapshot_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("portfolio_snapshots.id", ondelete="CASCADE"), index=True
    )
    ordinal: Mapped[int] = mapped_column(Integer)
    symbol: Mapped[str] = mapped_column(String(20), index=True)
    quantity: Mapped[Decimal] = mapped_column(Numeric(20, 8))
    market_value: Mapped[Decimal] = mapped_column(Numeric(20, 4))
    avg_entry_price: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    current_price: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    unrealized_pl: Mapped[Decimal] = mapped_column(Numeric(20, 4))
    unrealized_pl_pct: Mapped[Decimal] = mapped_column(Numeric(12, 8))
    weight: Mapped[Decimal] = mapped_column(Numeric(12, 8))


class WatchlistRecord(Base):
    __tablename__ = "watchlists"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    portfolio_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("portfolios.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class WatchlistSymbolRecord(Base):
    __tablename__ = "watchlist_symbols"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    watchlist_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("watchlists.id", ondelete="CASCADE"), index=True
    )
    symbol: Mapped[str] = mapped_column(String(20), index=True)
    added_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    __table_args__ = (UniqueConstraint("watchlist_id", "symbol"),)


class AgentDecisionRecord(Base):
    __tablename__ = "agent_decisions"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    workflow_run_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("workflow_runs.id", ondelete="CASCADE"), index=True
    )
    ordinal: Mapped[int] = mapped_column(Integer)
    agent_name: Mapped[str] = mapped_column(String(80), index=True)
    display_name: Mapped[str] = mapped_column(String(120))
    symbol: Mapped[str] = mapped_column(String(20), index=True)
    action: Mapped[str] = mapped_column(String(10), index=True)
    confidence: Mapped[Decimal] = mapped_column(Numeric(8, 6))
    thesis: Mapped[str] = mapped_column(Text)
    evidence: Mapped[list] = mapped_column(JSON_DOCUMENT)
    bullish_factors: Mapped[list] = mapped_column(JSON_DOCUMENT)
    bearish_factors: Mapped[list] = mapped_column(JSON_DOCUMENT)
    risk_flags: Mapped[list] = mapped_column(JSON_DOCUMENT)
    suggested_position_pct: Mapped[Decimal] = mapped_column(Numeric(10, 8))
    suggested_stop_loss_pct: Mapped[Decimal | None] = mapped_column(Numeric(10, 8))
    suggested_take_profit_pct: Mapped[Decimal | None] = mapped_column(Numeric(10, 8))
    invalidation_conditions: Mapped[list] = mapped_column(JSON_DOCUMENT)
    data_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    engine: Mapped[str] = mapped_column(String(80))
    latency_ms: Mapped[int] = mapped_column(Integer)
    input_hash: Mapped[str | None] = mapped_column(String(128), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    __table_args__ = (UniqueConstraint("workflow_run_id", "agent_name"),)


class ConsensusDecisionRecord(Base):
    __tablename__ = "consensus_decisions"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    workflow_run_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("workflow_runs.id", ondelete="CASCADE"), unique=True, index=True
    )
    direction: Mapped[str] = mapped_column(String(10), index=True)
    confidence: Mapped[Decimal] = mapped_column(Numeric(8, 6))
    weighted_score: Mapped[Decimal] = mapped_column(Numeric(10, 7))
    agreement_ratio: Mapped[Decimal] = mapped_column(Numeric(8, 6))
    disagreement_score: Mapped[Decimal] = mapped_column(Numeric(8, 6))
    agreeing_agents: Mapped[int] = mapped_column(Integer)
    total_agents: Mapped[int] = mapped_column(Integer)
    supporting_agents: Mapped[list] = mapped_column(JSON_DOCUMENT)
    dissenting_agents: Mapped[list] = mapped_column(JSON_DOCUMENT)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class RiskReviewRecord(Base):
    __tablename__ = "risk_reviews"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    workflow_run_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("workflow_runs.id", ondelete="CASCADE"), unique=True, index=True
    )
    verdict: Mapped[str] = mapped_column(String(40), index=True)
    semantic_risk_score: Mapped[Decimal] = mapped_column(Numeric(8, 6))
    issues: Mapped[list] = mapped_column(JSON_DOCUMENT)
    explanation: Mapped[str] = mapped_column(Text)
    engine: Mapped[str] = mapped_column(String(80))


class TradeProposalRecord(Base):
    __tablename__ = "trade_proposals"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    workflow_run_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("workflow_runs.id", ondelete="CASCADE"), unique=True, index=True
    )
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    side: Mapped[str] = mapped_column(String(10))
    consensus_confidence: Mapped[Decimal] = mapped_column(Numeric(8, 6))
    requested_position_pct: Mapped[Decimal] = mapped_column(Numeric(10, 8))
    requested_notional: Mapped[Decimal | None] = mapped_column(Numeric(20, 4))
    approved_position_pct: Mapped[Decimal | None] = mapped_column(Numeric(10, 8))
    approved_notional: Mapped[Decimal | None] = mapped_column(Numeric(20, 4))
    risk_decision: Mapped[str | None] = mapped_column(String(30))
    stop_loss_pct: Mapped[Decimal | None] = mapped_column(Numeric(10, 8))
    take_profit_pct: Mapped[Decimal | None] = mapped_column(Numeric(10, 8))
    supporting_agents: Mapped[list] = mapped_column(JSON_DOCUMENT)
    dissenting_agents: Mapped[list] = mapped_column(JSON_DOCUMENT)
    thesis: Mapped[str] = mapped_column(Text)
    invalidation_conditions: Mapped[list] = mapped_column(JSON_DOCUMENT)
    instrument_type: Mapped[str] = mapped_column(String(20), default="EQUITY")
    underlying_symbol: Mapped[str | None] = mapped_column(String(20), index=True)
    position_intent: Mapped[str | None] = mapped_column(String(30))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class RiskGateRecord(Base):
    __tablename__ = "risk_gate_results"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    workflow_run_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("workflow_runs.id", ondelete="CASCADE"), unique=True, index=True
    )
    decision: Mapped[str] = mapped_column(String(30), index=True)
    requested_position_pct: Mapped[Decimal] = mapped_column(Numeric(10, 8))
    approved_position_pct: Mapped[Decimal] = mapped_column(Numeric(10, 8))
    reasons: Mapped[list] = mapped_column(JSON_DOCUMENT)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class RiskCheckRecord(Base):
    __tablename__ = "risk_checks"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    workflow_run_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("workflow_runs.id", ondelete="CASCADE"), index=True
    )
    ordinal: Mapped[int] = mapped_column(Integer)
    rule_id: Mapped[str] = mapped_column(String(30), index=True)
    rule_name: Mapped[str] = mapped_column(String(120))
    passed: Mapped[bool] = mapped_column(Boolean, index=True)
    severity: Mapped[str] = mapped_column(String(20), index=True)
    measured_value: Mapped[dict | None] = mapped_column(JSON_DOCUMENT)
    threshold_value: Mapped[dict | None] = mapped_column(JSON_DOCUMENT)
    message: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    __table_args__ = (UniqueConstraint("workflow_run_id", "rule_id"),)


class ExecutionOrderRecord(Base):
    __tablename__ = "execution_orders"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    workflow_run_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("workflow_runs.id", ondelete="RESTRICT"), index=True
    )
    provider: Mapped[str] = mapped_column(String(40), default="alpaca")
    environment: Mapped[str] = mapped_column(String(20), default="paper")
    provider_order_id: Mapped[str | None] = mapped_column(String(255), unique=True)
    client_order_id: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    side: Mapped[str] = mapped_column(String(10))
    order_type: Mapped[str] = mapped_column(String(30), default="market")
    time_in_force: Mapped[str] = mapped_column(String(20), default="day")
    quantity: Mapped[Decimal | None] = mapped_column(Numeric(20, 8))
    notional: Mapped[Decimal] = mapped_column(Numeric(20, 4))
    status: Mapped[str] = mapped_column(String(50), index=True)
    execution_mode: Mapped[str] = mapped_column(String(32))
    risk_decision: Mapped[str] = mapped_column(String(30))
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    filled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    provider_response: Mapped[dict] = mapped_column(JSON_DOCUMENT)
    instrument_type: Mapped[str] = mapped_column(String(20), default="EQUITY")
    underlying_symbol: Mapped[str | None] = mapped_column(String(20), index=True)
    limit_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    position_intent: Mapped[str | None] = mapped_column(String(30))
    execution_interface: Mapped[str] = mapped_column(String(32), default="ALPACA_SDK")
    version_id: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    __mapper_args__ = {"version_id_col": version_id}


class ExplanationRecord(Base):
    __tablename__ = "explanations"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    workflow_run_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("workflow_runs.id", ondelete="CASCADE"), unique=True, index=True
    )
    headline: Mapped[str] = mapped_column(String(255))
    summary: Mapped[str] = mapped_column(Text)
    final_action: Mapped[str] = mapped_column(String(10))
    confidence: Mapped[Decimal] = mapped_column(Numeric(8, 6))
    positive_factors: Mapped[list] = mapped_column(JSON_DOCUMENT)
    negative_factors: Mapped[list] = mapped_column(JSON_DOCUMENT)
    agent_votes: Mapped[list] = mapped_column(JSON_DOCUMENT)
    consensus_explanation: Mapped[str] = mapped_column(Text)
    risk_decision: Mapped[str] = mapped_column(String(30))
    triggered_rules: Mapped[list] = mapped_column(JSON_DOCUMENT)
    requested_size: Mapped[Decimal] = mapped_column(Numeric(10, 8))
    approved_size: Mapped[Decimal] = mapped_column(Numeric(10, 8))
    invalidation_conditions: Mapped[list] = mapped_column(JSON_DOCUMENT)
    execution_status: Mapped[str | None] = mapped_column(String(50))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class AlertRecord(Base):
    __tablename__ = "soc_alerts"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    workflow_run_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("workflow_runs.id", ondelete="CASCADE"), index=True
    )
    rule_id: Mapped[str] = mapped_column(String(30), index=True)
    alert_type: Mapped[str] = mapped_column(String(80), index=True)
    severity: Mapped[str] = mapped_column(String(20), index=True)
    title: Mapped[str] = mapped_column(String(255))
    detail: Mapped[str] = mapped_column(Text)
    symbol: Mapped[str | None] = mapped_column(String(20), index=True)
    details: Mapped[dict] = mapped_column(JSON_DOCUMENT)
    status: Mapped[str] = mapped_column(String(30), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    version_id: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    __mapper_args__ = {"version_id_col": version_id}


class AuditEventRecord(Base):
    __tablename__ = "audit_events"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    workflow_run_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("workflow_runs.id", ondelete="CASCADE"), index=True
    )
    ordinal: Mapped[int] = mapped_column(Integer)
    event_type: Mapped[str] = mapped_column(String(80), index=True)
    actor_type: Mapped[str] = mapped_column(String(50))
    actor_name: Mapped[str | None] = mapped_column(String(100))
    title: Mapped[str] = mapped_column(String(255))
    detail: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(30))
    payload: Mapped[dict] = mapped_column(JSON_DOCUMENT)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class RiskPolicyRecord(Base):
    __tablename__ = "risk_policies"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    portfolio_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("portfolios.id", ondelete="CASCADE"), index=True
    )
    policy_key: Mapped[str] = mapped_column(String(100), index=True)
    policy_value: Mapped[dict] = mapped_column(JSON_DOCUMENT)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    version_id: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    __table_args__ = (UniqueConstraint("portfolio_id", "policy_key"),)
    __mapper_args__ = {"version_id_col": version_id}


class WorkflowErrorRecord(Base):
    __tablename__ = "workflow_errors"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    workflow_run_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("workflow_runs.id", ondelete="CASCADE"), index=True
    )
    ordinal: Mapped[int] = mapped_column(Integer)
    message: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


settings = get_settings()
connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
engine = create_engine(
    settings.database_url,
    connect_args=connect_args,
    pool_pre_ping=not settings.database_url.startswith("sqlite"),
)


if settings.database_url.startswith("sqlite"):
    @event.listens_for(engine, "connect")
    def _sqlite_foreign_keys(dbapi_connection, _connection_record) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def run_migrations() -> None:
    from alembic import command
    from alembic.config import Config

    api_root = Path(__file__).resolve().parents[1]
    config = Config(str(api_root / "alembic.ini"))
    config.set_main_option("script_location", str(api_root / "migrations"))
    config.set_main_option("sqlalchemy.url", settings.database_url.replace("%", "%%"))
    with engine.connect() as connection:
        config.attributes["connection"] = connection
        migration_lock_key = 7_309_861_047_251
        if connection.dialect.name == "postgresql":
            connection.execute(
                text("SELECT pg_advisory_lock(:key)"), {"key": migration_lock_key}
            )
        try:
            command.upgrade(config, "head")
        finally:
            if connection.dialect.name == "postgresql":
                connection.execute(
                    text("SELECT pg_advisory_unlock(:key)"),
                    {"key": migration_lock_key},
                )


def init_db() -> None:
    if settings.run_migrations_on_startup:
        run_migrations()
        backfill_legacy_workflows()
        ensure_system_records()
    else:
        Base.metadata.create_all(bind=engine)


def backfill_legacy_workflows() -> int:
    """Normalize pre-migration workflow JSON after the schema upgrade.

    This is idempotent: ``save_workflow`` clears ``legacy_data`` in the same
    transaction that writes all normalized child rows.
    """
    migrated = 0
    with SessionLocal() as db:
        records = db.scalars(
            select(WorkflowRecord).where(WorkflowRecord.legacy_data.is_not(None))
        ).all()
        repository = Repository(db)
        for record in records:
            if record.legacy_data:
                repository.save_workflow(dict(record.legacy_data))
                migrated += 1
    return migrated


def ensure_system_records() -> None:
    with SessionLocal() as db:
        repository = Repository(db)
        portfolio_id = repository.ensure_system_portfolio()
        for record in db.scalars(
            select(WorkflowRecord).where(WorkflowRecord.portfolio_id.is_(None))
        ).all():
            record.portfolio_id = portfolio_id
        db.commit()


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _stable_id(run_id: str, kind: str, ordinal: int = 0) -> str:
    return str(uuid5(ID_NAMESPACE, f"{run_id}:{kind}:{ordinal}"))


def _dt(value: datetime | str | None) -> datetime | None:
    if value is None or isinstance(value, datetime):
        return value
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.isoformat()


def _number(value: Decimal | float | int | None) -> float | None:
    return float(value) if value is not None else None


class Repository:
    def __init__(self, db: Session, coordination: CoordinationBackend | None = None):
        self.db = db
        self.coordination = coordination or get_coordination()

    def ensure_system_portfolio(self) -> str:
        now = utcnow()
        if self.db.get(UserRecord, SYSTEM_USER_ID) is None:
            self.db.add(
                UserRecord(
                    id=SYSTEM_USER_ID,
                    email=None,
                    display_name="SentinelAlpha Demo User",
                    created_at=now,
                )
            )
            self.db.flush()
        if self.db.get(PortfolioRecord, SYSTEM_PORTFOLIO_ID) is None:
            self.db.add(
                PortfolioRecord(
                    id=SYSTEM_PORTFOLIO_ID,
                    user_id=SYSTEM_USER_ID,
                    name="Primary Alpaca Paper Portfolio",
                    provider="alpaca",
                    environment="paper",
                    created_at=now,
                )
            )
        self.db.flush()
        return SYSTEM_PORTFOLIO_ID

    def create_workflow_run(
        self,
        run_id: str,
        *,
        symbol: str,
        mode: str,
        scenario: str,
        agent_provider: str,
        strategy: str = "EQUITY",
        replay_of: str | None = None,
        portfolio_id: str | None = None,
    ) -> None:
        if self.db.get(WorkflowRecord, run_id):
            return
        now = utcnow()
        portfolio_id = portfolio_id or self.ensure_system_portfolio()
        if self.db.get(PortfolioRecord, portfolio_id) is None:
            raise ValueError("authenticated portfolio does not exist")
        self.db.add(
            WorkflowRecord(
                id=run_id,
                portfolio_id=portfolio_id,
                replay_of=replay_of,
                symbol=symbol,
                trigger_type="replay" if replay_of else "manual",
                status="RUNNING",
                mode=mode,
                scenario=scenario,
                agent_provider=agent_provider,
                strategy=strategy,
                started_at=now,
                completed_at=None,
                updated_at=now,
                final_decision=None,
                final_confidence=None,
                error_message=None,
                version_id=1,
                legacy_data=None,
                hedge_plan=None,
            )
        )
        self.db.commit()

    def fail_workflow(self, run_id: str, exc: Exception) -> None:
        record = self.db.get(WorkflowRecord, run_id)
        if record is None:
            return
        record.status = "FAILED"
        record.error_message = f"{type(exc).__name__}: {str(exc)[:1000]}"
        record.completed_at = utcnow()
        record.updated_at = utcnow()
        self.db.commit()
        self.coordination.delete(f"workflow:{run_id}")

    def _clear_workflow_details(self, run_id: str) -> None:
        models = (
            PositionRecord,
            PortfolioSnapshotRecord,
            MarketSnapshotRecord,
            NewsItemRecord,
            AgentDecisionRecord,
            ConsensusDecisionRecord,
            RiskReviewRecord,
            TradeProposalRecord,
            RiskCheckRecord,
            RiskGateRecord,
            ExplanationRecord,
            AuditEventRecord,
            WorkflowErrorRecord,
        )
        for model in models:
            self.db.execute(delete(model).where(model.workflow_run_id == run_id))
        self.db.flush()

    def save_workflow(self, payload: dict) -> None:
        run_id = payload["workflow_run_id"]
        now = utcnow()
        replay_of = payload.get("replay_of")
        # Legacy SQLite rows had no replay foreign key. Preserve valid links,
        # but do not let an orphaned historical identifier abort normalization.
        if replay_of and self.db.get(WorkflowRecord, replay_of) is None:
            replay_of = None
        try:
            record = self.db.get(WorkflowRecord, run_id)
            if record is None:
                portfolio_id = self.ensure_system_portfolio()
                record = WorkflowRecord(
                    id=run_id,
                    portfolio_id=portfolio_id,
                    replay_of=replay_of,
                    symbol=payload["symbol"],
                    trigger_type="replay" if payload.get("replay_of") else "manual",
                    status=payload["status"],
                    mode=payload["mode"],
                    scenario=payload["scenario"],
                    agent_provider=payload["agent_provider"],
                    strategy=payload.get("strategy", "EQUITY"),
                    started_at=_dt(payload["created_at"]),
                    completed_at=_dt(payload.get("completed_at")),
                    updated_at=now,
                    final_decision=payload["consensus"]["direction"],
                    final_confidence=payload["consensus"]["confidence"],
                    error_message="\n".join(payload.get("errors", [])) or None,
                    version_id=1,
                    legacy_data=None,
                    hedge_plan=payload.get("hedge_plan"),
                )
                self.db.add(record)
                self.db.flush()
            else:
                if record.portfolio_id is None:
                    record.portfolio_id = self.ensure_system_portfolio()
                record.replay_of = replay_of
                record.symbol = payload["symbol"]
                record.status = payload["status"]
                record.mode = payload["mode"]
                record.scenario = payload["scenario"]
                record.agent_provider = payload["agent_provider"]
                record.strategy = payload.get("strategy", "EQUITY")
                record.started_at = _dt(payload["created_at"])
                record.completed_at = _dt(payload.get("completed_at"))
                record.updated_at = now
                record.final_decision = payload["consensus"]["direction"]
                record.final_confidence = payload["consensus"]["confidence"]
                record.error_message = "\n".join(payload.get("errors", [])) or None
                record.legacy_data = None
                record.hedge_plan = payload.get("hedge_plan")

            self._clear_workflow_details(run_id)
            self._persist_market(run_id, payload["market_snapshot"])
            self._persist_news(run_id, payload["symbol"], payload["news_items"])
            self._persist_account(run_id, payload["account"], now)
            self._persist_agent_decisions(run_id, payload["agent_decisions"], now)
            self._persist_consensus(run_id, payload["consensus"], now)
            self._persist_risk_review(run_id, payload["risk_review"])
            self._persist_proposal(run_id, payload.get("proposal"), payload["risk_gate"], now)
            self._persist_risk_gate(run_id, payload["risk_gate"], now)
            self._persist_explanation(run_id, payload["explanation"], now)
            self._persist_audit_events(run_id, payload["timeline"])
            self._persist_errors(run_id, payload.get("errors", []), now)
            for alert in payload.get("soc_alerts", []):
                self._persist_alert(alert, now)
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise
        self.coordination.delete(f"workflow:{run_id}")

    def _persist_market(self, run_id: str, market: dict) -> None:
        self.db.add(
            MarketSnapshotRecord(
                id=_stable_id(run_id, "market"),
                workflow_run_id=run_id,
                symbol=market["symbol"],
                price=market["price"],
                change_pct=market["change_pct"],
                snapshot_time=_dt(market["as_of"]),
                source=market["source"],
                features=market["indicators"],
                bars=market["bars"],
            )
        )

    def _persist_news(self, run_id: str, symbol: str, items: list[dict]) -> None:
        for index, item in enumerate(items):
            self.db.add(
                NewsItemRecord(
                    id=_stable_id(run_id, "news", index),
                    workflow_run_id=run_id,
                    external_id=item.get("id"),
                    symbol=symbol,
                    headline=item["headline"],
                    summary=item["summary"],
                    source=item["source"],
                    published_at=_dt(item["published_at"]),
                    sentiment=item["sentiment"],
                    relevance=item["relevance"],
                    corroborated=item["corroborated"],
                    duplicate_group=item.get("duplicate_group"),
                    information_risk=item.get("information_risk", []),
                    metadata_json={},
                )
            )

    def _persist_account(self, run_id: str, account: dict, now: datetime) -> None:
        snapshot_id = _stable_id(run_id, "portfolio")
        self.db.add(
            PortfolioSnapshotRecord(
                id=snapshot_id,
                workflow_run_id=run_id,
                account_id=account["account_id"],
                account_status=account["status"],
                currency=account["currency"],
                equity=account["equity"],
                cash=account["cash"],
                buying_power=account["buying_power"],
                options_buying_power=account.get("options_buying_power"),
                options_approved_level=account.get("options_approved_level", 0),
                options_trading_level=account.get("options_trading_level", 0),
                day_pl=account["day_pl"],
                day_pl_pct=account["day_pl_pct"],
                portfolio_drawdown_pct=account["portfolio_drawdown_pct"],
                trades_today=account["trades_today"],
                open_orders=account.get("open_orders", []),
                source=account["source"],
                captured_at=now,
            )
        )
        for index, item in enumerate(account["positions"]):
            self.db.add(
                PositionRecord(
                    id=_stable_id(run_id, "position", index),
                    workflow_run_id=run_id,
                    portfolio_snapshot_id=snapshot_id,
                    ordinal=index,
                    **item,
                )
            )

    def _persist_agent_decisions(self, run_id: str, items: list[dict], now: datetime) -> None:
        for index, item in enumerate(items):
            self.db.add(
                AgentDecisionRecord(
                    id=_stable_id(run_id, "agent", index),
                    workflow_run_id=run_id,
                    ordinal=index,
                    agent_name=item["agent_name"],
                    display_name=item["display_name"],
                    symbol=item["symbol"],
                    action=item["action"],
                    confidence=item["confidence"],
                    thesis=item["thesis"],
                    evidence=item["evidence"],
                    bullish_factors=item["bullish_factors"],
                    bearish_factors=item["bearish_factors"],
                    risk_flags=item["risk_flags"],
                    suggested_position_pct=item["suggested_position_pct"],
                    suggested_stop_loss_pct=item.get("suggested_stop_loss_pct"),
                    suggested_take_profit_pct=item.get("suggested_take_profit_pct"),
                    invalidation_conditions=item["invalidation_conditions"],
                    data_timestamp=_dt(item["data_timestamp"]),
                    engine=item.get("engine", "rules-v1"),
                    latency_ms=item.get("latency_ms", 0),
                    input_hash=None,
                    created_at=now,
                )
            )

    def _persist_consensus(self, run_id: str, item: dict, now: datetime) -> None:
        self.db.add(
            ConsensusDecisionRecord(
                id=_stable_id(run_id, "consensus"),
                workflow_run_id=run_id,
                created_at=now,
                **item,
            )
        )

    def _persist_risk_review(self, run_id: str, item: dict) -> None:
        self.db.add(
            RiskReviewRecord(
                id=_stable_id(run_id, "risk-review"),
                workflow_run_id=run_id,
                **item,
            )
        )

    def _persist_proposal(self, run_id: str, item: dict | None, gate: dict, now: datetime) -> None:
        if item is None:
            return
        requested_notional = item.get("requested_notional")
        approved_pct = gate["approved_position_pct"]
        approved_notional = (
            requested_notional * approved_pct / item["requested_position_pct"]
            if requested_notional is not None and item["requested_position_pct"]
            else None
        )
        values = dict(item)
        values.pop("workflow_run_id", None)
        values.pop("hedge_plan", None)
        self.db.add(
            TradeProposalRecord(
                id=_stable_id(run_id, "proposal"),
                workflow_run_id=run_id,
                approved_position_pct=approved_pct,
                approved_notional=approved_notional,
                risk_decision=gate["decision"],
                created_at=now,
                **values,
            )
        )

    def _persist_risk_gate(self, run_id: str, item: dict, now: datetime) -> None:
        self.db.add(
            RiskGateRecord(
                id=_stable_id(run_id, "risk-gate"),
                workflow_run_id=run_id,
                decision=item["decision"],
                requested_position_pct=item["requested_position_pct"],
                approved_position_pct=item["approved_position_pct"],
                reasons=item["reasons"],
                created_at=now,
            )
        )
        for index, check in enumerate(item["checks"]):
            self.db.add(
                RiskCheckRecord(
                    id=_stable_id(run_id, "risk-check", index),
                    workflow_run_id=run_id,
                    ordinal=index,
                    measured_value=None,
                    threshold_value=None,
                    created_at=now,
                    **check,
                )
            )

    def _persist_explanation(self, run_id: str, item: dict, now: datetime) -> None:
        self.db.add(
            ExplanationRecord(
                id=_stable_id(run_id, "explanation"),
                workflow_run_id=run_id,
                created_at=now,
                **item,
            )
        )

    def _persist_audit_events(self, run_id: str, items: list[dict]) -> None:
        for index, item in enumerate(items):
            self.db.add(
                AuditEventRecord(
                    id=item["id"],
                    workflow_run_id=run_id,
                    ordinal=index,
                    event_type=item["event"],
                    actor_type="system",
                    actor_name="sentinelalpha",
                    title=item["title"],
                    detail=item["detail"],
                    status=item["status"],
                    payload={},
                    created_at=_dt(item["timestamp"]),
                )
            )

    def _persist_errors(self, run_id: str, errors: list[str], now: datetime) -> None:
        for index, message in enumerate(errors):
            self.db.add(
                WorkflowErrorRecord(
                    id=_stable_id(run_id, "error", index),
                    workflow_run_id=run_id,
                    ordinal=index,
                    message=message,
                    created_at=now,
                )
            )

    def get_workflow(self, run_id: str, *, for_update: bool = False) -> dict | None:
        if not for_update:
            cached = self.coordination.get_json(f"workflow:{run_id}")
            if cached is not None:
                return cached
        query = select(WorkflowRecord).where(WorkflowRecord.id == run_id)
        if for_update and self.db.bind and self.db.bind.dialect.name != "sqlite":
            query = query.with_for_update()
        record = self.db.scalar(query)
        if record is None:
            return None
        payload = self._workflow_payload(record)
        if payload is not None and not for_update:
            self.coordination.set_json(f"workflow:{run_id}", payload)
        return payload

    def _workflow_payload(self, record: WorkflowRecord) -> dict | None:
        if record.legacy_data:
            return record.legacy_data
        market = self.db.scalar(
            select(MarketSnapshotRecord).where(MarketSnapshotRecord.workflow_run_id == record.id)
        )
        account = self.db.scalar(
            select(PortfolioSnapshotRecord).where(PortfolioSnapshotRecord.workflow_run_id == record.id)
        )
        consensus = self.db.scalar(
            select(ConsensusDecisionRecord).where(ConsensusDecisionRecord.workflow_run_id == record.id)
        )
        risk_review = self.db.scalar(
            select(RiskReviewRecord).where(RiskReviewRecord.workflow_run_id == record.id)
        )
        risk_gate = self.db.scalar(
            select(RiskGateRecord).where(RiskGateRecord.workflow_run_id == record.id)
        )
        explanation = self.db.scalar(
            select(ExplanationRecord).where(ExplanationRecord.workflow_run_id == record.id)
        )
        if not all((market, account, consensus, risk_review, risk_gate, explanation)):
            return None

        news = self.db.scalars(
            select(NewsItemRecord)
            .where(NewsItemRecord.workflow_run_id == record.id)
            .order_by(NewsItemRecord.published_at.desc())
        ).all()
        positions = self.db.scalars(
            select(PositionRecord)
            .where(PositionRecord.workflow_run_id == record.id)
            .order_by(PositionRecord.ordinal)
        ).all()
        agents = self.db.scalars(
            select(AgentDecisionRecord)
            .where(AgentDecisionRecord.workflow_run_id == record.id)
            .order_by(AgentDecisionRecord.ordinal)
        ).all()
        proposal = self.db.scalar(
            select(TradeProposalRecord).where(TradeProposalRecord.workflow_run_id == record.id)
        )
        checks = self.db.scalars(
            select(RiskCheckRecord)
            .where(RiskCheckRecord.workflow_run_id == record.id)
            .order_by(RiskCheckRecord.ordinal)
        ).all()
        order = self.db.scalar(
            select(ExecutionOrderRecord).where(ExecutionOrderRecord.workflow_run_id == record.id)
        )
        alerts = self.db.scalars(
            select(AlertRecord)
            .where(AlertRecord.workflow_run_id == record.id)
            .order_by(AlertRecord.created_at)
        ).all()
        events = self.db.scalars(
            select(AuditEventRecord)
            .where(AuditEventRecord.workflow_run_id == record.id)
            .order_by(AuditEventRecord.ordinal)
        ).all()
        errors = self.db.scalars(
            select(WorkflowErrorRecord)
            .where(WorkflowErrorRecord.workflow_run_id == record.id)
            .order_by(WorkflowErrorRecord.ordinal)
        ).all()

        return {
            "workflow_run_id": record.id,
            "symbol": record.symbol,
            "status": record.status,
            "mode": record.mode,
            "scenario": record.scenario,
            "agent_provider": record.agent_provider,
            "strategy": record.strategy or "EQUITY",
            "replay_of": record.replay_of,
            "created_at": _iso(record.started_at),
            "completed_at": _iso(record.completed_at),
            "market_snapshot": {
                "symbol": market.symbol,
                "price": _number(market.price),
                "change_pct": _number(market.change_pct),
                "as_of": _iso(market.snapshot_time),
                "source": market.source,
                "bars": market.bars,
                "indicators": market.features,
            },
            "news_items": [
                {
                    "id": item.external_id or item.id,
                    "headline": item.headline,
                    "summary": item.summary,
                    "source": item.source,
                    "published_at": _iso(item.published_at),
                    "sentiment": _number(item.sentiment),
                    "relevance": _number(item.relevance),
                    "corroborated": item.corroborated,
                    "duplicate_group": item.duplicate_group,
                    "information_risk": item.information_risk,
                }
                for item in news
            ],
            "account": {
                "account_id": account.account_id,
                "status": account.account_status,
                "currency": account.currency,
                "equity": _number(account.equity),
                "cash": _number(account.cash),
                "buying_power": _number(account.buying_power),
                "options_buying_power": _number(account.options_buying_power),
                "options_approved_level": account.options_approved_level,
                "options_trading_level": account.options_trading_level,
                "day_pl": _number(account.day_pl),
                "day_pl_pct": _number(account.day_pl_pct),
                "portfolio_drawdown_pct": _number(account.portfolio_drawdown_pct),
                "trades_today": account.trades_today,
                "positions": [
                    {
                        "symbol": item.symbol,
                        "quantity": _number(item.quantity),
                        "market_value": _number(item.market_value),
                        "avg_entry_price": _number(item.avg_entry_price),
                        "current_price": _number(item.current_price),
                        "unrealized_pl": _number(item.unrealized_pl),
                        "unrealized_pl_pct": _number(item.unrealized_pl_pct),
                        "weight": _number(item.weight),
                    }
                    for item in positions
                ],
                "open_orders": account.open_orders,
                "source": account.source,
            },
            "agent_decisions": [
                {
                    "agent_name": item.agent_name,
                    "display_name": item.display_name,
                    "symbol": item.symbol,
                    "action": item.action,
                    "confidence": _number(item.confidence),
                    "thesis": item.thesis,
                    "evidence": item.evidence,
                    "bullish_factors": item.bullish_factors,
                    "bearish_factors": item.bearish_factors,
                    "risk_flags": item.risk_flags,
                    "suggested_position_pct": _number(item.suggested_position_pct),
                    "suggested_stop_loss_pct": _number(item.suggested_stop_loss_pct),
                    "suggested_take_profit_pct": _number(item.suggested_take_profit_pct),
                    "invalidation_conditions": item.invalidation_conditions,
                    "data_timestamp": _iso(item.data_timestamp),
                    "engine": item.engine,
                    "latency_ms": item.latency_ms,
                }
                for item in agents
            ],
            "consensus": {
                "direction": consensus.direction,
                "confidence": _number(consensus.confidence),
                "weighted_score": _number(consensus.weighted_score),
                "agreement_ratio": _number(consensus.agreement_ratio),
                "disagreement_score": _number(consensus.disagreement_score),
                "agreeing_agents": consensus.agreeing_agents,
                "total_agents": consensus.total_agents,
                "supporting_agents": consensus.supporting_agents,
                "dissenting_agents": consensus.dissenting_agents,
            },
            "risk_review": {
                "verdict": risk_review.verdict,
                "semantic_risk_score": _number(risk_review.semantic_risk_score),
                "issues": risk_review.issues,
                "explanation": risk_review.explanation,
                "engine": risk_review.engine,
            },
            "proposal": self._proposal_payload(proposal, record.hedge_plan),
            "hedge_plan": record.hedge_plan,
            "risk_gate": {
                "decision": risk_gate.decision,
                "requested_position_pct": _number(risk_gate.requested_position_pct),
                "approved_position_pct": _number(risk_gate.approved_position_pct),
                "checks": [
                    {
                        "rule_id": item.rule_id,
                        "rule_name": item.rule_name,
                        "passed": item.passed,
                        "severity": item.severity,
                        "message": item.message,
                    }
                    for item in checks
                ],
                "reasons": risk_gate.reasons,
            },
            "execution": self._order_payload(order),
            "explanation": {
                "headline": explanation.headline,
                "summary": explanation.summary,
                "final_action": explanation.final_action,
                "confidence": _number(explanation.confidence),
                "positive_factors": explanation.positive_factors,
                "negative_factors": explanation.negative_factors,
                "agent_votes": explanation.agent_votes,
                "consensus_explanation": explanation.consensus_explanation,
                "risk_decision": explanation.risk_decision,
                "triggered_rules": explanation.triggered_rules,
                "requested_size": _number(explanation.requested_size),
                "approved_size": _number(explanation.approved_size),
                "invalidation_conditions": explanation.invalidation_conditions,
                "execution_status": explanation.execution_status,
            },
            "soc_alerts": [self._alert_payload(item) for item in alerts],
            "timeline": [
                {
                    "id": item.id,
                    "event": item.event_type,
                    "title": item.title,
                    "detail": item.detail,
                    "status": item.status,
                    "timestamp": _iso(item.created_at),
                }
                for item in events
            ],
            "errors": [item.message for item in errors],
        }

    @staticmethod
    def _proposal_payload(
        item: TradeProposalRecord | None, hedge_plan: dict | None = None
    ) -> dict | None:
        if item is None:
            return None
        return {
            "workflow_run_id": item.workflow_run_id,
            "symbol": item.symbol,
            "side": item.side,
            "consensus_confidence": _number(item.consensus_confidence),
            "requested_position_pct": _number(item.requested_position_pct),
            "requested_notional": _number(item.requested_notional),
            "stop_loss_pct": _number(item.stop_loss_pct),
            "take_profit_pct": _number(item.take_profit_pct),
            "supporting_agents": item.supporting_agents,
            "dissenting_agents": item.dissenting_agents,
            "thesis": item.thesis,
            "invalidation_conditions": item.invalidation_conditions,
            "instrument_type": item.instrument_type or "EQUITY",
            "underlying_symbol": item.underlying_symbol,
            "position_intent": item.position_intent,
            "hedge_plan": hedge_plan,
        }

    @staticmethod
    def _order_payload(item: ExecutionOrderRecord | None) -> dict | None:
        if item is None:
            return None
        return {
            "id": item.id,
            "provider_order_id": item.provider_order_id,
            "client_order_id": item.client_order_id,
            "workflow_run_id": item.workflow_run_id,
            "symbol": item.symbol,
            "side": item.side,
            "notional": _number(item.notional),
            "quantity": _number(item.quantity),
            "status": item.status,
            "execution_mode": item.execution_mode,
            "submitted_at": _iso(item.submitted_at),
            "filled_at": _iso(item.filled_at),
            "risk_decision": item.risk_decision,
            "instrument_type": item.instrument_type or "EQUITY",
            "underlying_symbol": item.underlying_symbol,
            "order_type": item.order_type,
            "limit_price": _number(item.limit_price),
            "position_intent": item.position_intent,
            "execution_interface": item.execution_interface or "ALPACA_SDK",
        }

    @staticmethod
    def _alert_payload(item: AlertRecord) -> dict:
        return {
            "id": item.id,
            "rule_id": item.rule_id,
            "alert_type": item.alert_type,
            "severity": item.severity,
            "title": item.title,
            "detail": item.detail,
            "symbol": item.symbol,
            "workflow_run_id": item.workflow_run_id,
            "status": item.status,
            "created_at": _iso(item.created_at),
        }

    def workflow_portfolio_id(self, run_id: str) -> str | None:
        return self.db.scalar(
            select(WorkflowRecord.portfolio_id).where(WorkflowRecord.id == run_id)
        )

    def list_workflows(
        self,
        limit: int = 50,
        *,
        portfolio_ids: frozenset[str] | None = None,
    ) -> list[dict]:
        if portfolio_ids is not None and not portfolio_ids:
            return []
        query = select(WorkflowRecord).where(WorkflowRecord.status != "RUNNING")
        if portfolio_ids is not None:
            query = query.where(WorkflowRecord.portfolio_id.in_(portfolio_ids))
        records = self.db.scalars(
            query.order_by(WorkflowRecord.started_at.desc()).limit(limit)
        ).all()
        return [payload for record in records if (payload := self._workflow_payload(record))]

    def save_order(self, payload: dict, *, commit: bool = True) -> None:
        existing = self.db.get(ExecutionOrderRecord, payload["id"])
        if existing is None:
            existing = self.db.scalar(
                select(ExecutionOrderRecord).where(
                    ExecutionOrderRecord.client_order_id == payload["client_order_id"]
                )
            )
        if existing is not None:
            return
        now = utcnow()
        self.db.add(
            ExecutionOrderRecord(
                id=payload["id"],
                provider="alpaca",
                environment="paper",
                provider_order_id=payload["provider_order_id"],
                client_order_id=payload["client_order_id"],
                workflow_run_id=payload["workflow_run_id"],
                symbol=payload["symbol"],
                side=payload["side"],
                order_type=payload.get("order_type", "market"),
                time_in_force="day",
                quantity=payload.get("quantity"),
                notional=payload["notional"],
                status=payload["status"],
                execution_mode=payload["execution_mode"],
                risk_decision=payload["risk_decision"],
                submitted_at=_dt(payload["submitted_at"]),
                filled_at=_dt(payload.get("filled_at")),
                updated_at=now,
                provider_response={},
                instrument_type=payload.get("instrument_type", "EQUITY"),
                underlying_symbol=payload.get("underlying_symbol"),
                limit_price=payload.get("limit_price"),
                position_intent=payload.get("position_intent"),
                execution_interface=payload.get("execution_interface", "ALPACA_SDK"),
                version_id=1,
            )
        )
        if commit:
            self.db.commit()
            self.coordination.delete(f"workflow:{payload['workflow_run_id']}")

    def get_order(self, order_id: str) -> dict | None:
        record = self.db.get(ExecutionOrderRecord, order_id)
        if record is None:
            record = self.db.scalar(
                select(ExecutionOrderRecord).where(
                    ExecutionOrderRecord.provider_order_id == order_id
                )
            )
        return self._order_payload(record)

    def order_portfolio_id(self, order_id: str) -> str | None:
        return self.db.scalar(
            select(WorkflowRecord.portfolio_id)
            .join(
                ExecutionOrderRecord,
                ExecutionOrderRecord.workflow_run_id == WorkflowRecord.id,
            )
            .where(
                (ExecutionOrderRecord.id == order_id)
                | (ExecutionOrderRecord.provider_order_id == order_id)
            )
        )

    def list_orders(
        self,
        limit: int = 100,
        *,
        portfolio_ids: frozenset[str] | None = None,
    ) -> list[dict]:
        if portfolio_ids is not None and not portfolio_ids:
            return []
        query = select(ExecutionOrderRecord)
        if portfolio_ids is not None:
            query = query.join(
                WorkflowRecord,
                WorkflowRecord.id == ExecutionOrderRecord.workflow_run_id,
            ).where(WorkflowRecord.portfolio_id.in_(portfolio_ids))
        records = self.db.scalars(
            query.order_by(ExecutionOrderRecord.submitted_at.desc()).limit(limit)
        ).all()
        return [self._order_payload(record) for record in records]

    def has_active_intent(self, symbol: str, side: str, exclude_run_id: str | None = None) -> bool:
        query = select(ExecutionOrderRecord.id).where(
            ExecutionOrderRecord.symbol == symbol,
            ExecutionOrderRecord.side == side,
            ExecutionOrderRecord.status.in_(["accepted", "new", "pending_new", "partially_filled"]),
        )
        if exclude_run_id:
            query = query.where(ExecutionOrderRecord.workflow_run_id != exclude_run_id)
        return self.db.scalar(query.limit(1)) is not None

    def trades_today(self) -> int:
        start = datetime.combine(utcnow().date(), datetime.min.time(), tzinfo=timezone.utc)
        return int(
            self.db.scalar(
                select(func.count(ExecutionOrderRecord.id)).where(
                    ExecutionOrderRecord.submitted_at >= start
                )
            )
            or 0
        )

    def _persist_alert(self, payload: dict, now: datetime | None = None) -> None:
        timestamp = now or utcnow()
        record = self.db.get(AlertRecord, payload["id"])
        if record is None:
            record = AlertRecord(
                id=payload["id"],
                workflow_run_id=payload.get("workflow_run_id"),
                rule_id=payload["rule_id"],
                alert_type=payload["alert_type"],
                severity=payload["severity"],
                title=payload["title"],
                detail=payload["detail"],
                symbol=payload.get("symbol"),
                details={},
                status=payload["status"],
                created_at=_dt(payload["created_at"]),
                updated_at=timestamp,
                resolved_at=timestamp if payload["status"] == "RESOLVED" else None,
                version_id=1,
            )
            self.db.add(record)
        else:
            record.rule_id = payload["rule_id"]
            record.alert_type = payload["alert_type"]
            record.severity = payload["severity"]
            record.title = payload["title"]
            record.detail = payload["detail"]
            record.symbol = payload.get("symbol")
            record.details = {}
            record.status = payload["status"]
            record.updated_at = timestamp
            record.resolved_at = timestamp if payload["status"] == "RESOLVED" else None

    def save_alert(self, payload: dict) -> None:
        self._persist_alert(payload)
        self.db.commit()
        if payload.get("workflow_run_id"):
            self.coordination.delete(f"workflow:{payload['workflow_run_id']}")

    def alert_portfolio_id(self, alert_id: str) -> str | None:
        return self.db.scalar(
            select(WorkflowRecord.portfolio_id)
            .join(AlertRecord, AlertRecord.workflow_run_id == WorkflowRecord.id)
            .where(AlertRecord.id == alert_id)
        )

    def list_alerts(
        self,
        limit: int = 100,
        *,
        portfolio_ids: frozenset[str] | None = None,
    ) -> list[dict]:
        if portfolio_ids is not None and not portfolio_ids:
            return []
        query = select(AlertRecord)
        if portfolio_ids is not None:
            query = query.join(
                WorkflowRecord, WorkflowRecord.id == AlertRecord.workflow_run_id
            ).where(WorkflowRecord.portfolio_id.in_(portfolio_ids))
        records = self.db.scalars(
            query.order_by(AlertRecord.created_at.desc()).limit(limit)
        ).all()
        return [self._alert_payload(record) for record in records]

    def get_alert(self, alert_id: str) -> dict | None:
        record = self.db.get(AlertRecord, alert_id)
        return self._alert_payload(record) if record else None

    def update_alert(
        self,
        alert_id: str,
        status: str,
        *,
        portfolio_ids: frozenset[str] | None = None,
    ) -> dict | None:
        if portfolio_ids is not None and not portfolio_ids:
            return None
        query = select(AlertRecord).where(AlertRecord.id == alert_id)
        if portfolio_ids is not None:
            query = query.join(
                WorkflowRecord, WorkflowRecord.id == AlertRecord.workflow_run_id
            ).where(WorkflowRecord.portfolio_id.in_(portfolio_ids))
        if self.db.bind and self.db.bind.dialect.name != "sqlite":
            query = query.with_for_update()
        record = self.db.scalar(query)
        if record is None:
            return None
        now = utcnow()
        record.status = status
        record.updated_at = now
        record.resolved_at = now if status == "RESOLVED" else None
        self.db.commit()
        if record.workflow_run_id:
            self.coordination.delete(f"workflow:{record.workflow_run_id}")
        return self._alert_payload(record)

    def seed_risk_policies(self, policies: list[dict]) -> None:
        portfolio_id = self.ensure_system_portfolio()
        now = utcnow()
        existing = {
            record.policy_key
            for record in self.db.scalars(
                select(RiskPolicyRecord).where(
                    RiskPolicyRecord.portfolio_id == portfolio_id
                )
            ).all()
        }
        for policy in policies:
            if policy["key"] in existing:
                continue
            self.db.add(
                RiskPolicyRecord(
                    id=_stable_id(portfolio_id, f"policy:{policy['key']}"),
                    portfolio_id=portfolio_id,
                    policy_key=policy["key"],
                    policy_value=policy,
                    enabled=True,
                    updated_at=now,
                    version_id=1,
                )
            )
        if "kill_switch" not in existing:
            self.db.add(
                RiskPolicyRecord(
                    id=_stable_id(portfolio_id, "policy:kill_switch"),
                    portfolio_id=portfolio_id,
                    policy_key="kill_switch",
                    policy_value={"value": False},
                    enabled=True,
                    updated_at=now,
                    version_id=1,
                )
            )
        self.db.commit()

    def runtime_risk_controls(self) -> tuple[dict[str, Any], bool]:
        records = self.db.scalars(
            select(RiskPolicyRecord).where(
                RiskPolicyRecord.portfolio_id == SYSTEM_PORTFOLIO_ID,
                RiskPolicyRecord.enabled.is_(True),
            )
        ).all()
        values: dict[str, Any] = {}
        kill_switch = False
        for record in records:
            value = record.policy_value.get("value")
            if record.policy_key == "kill_switch":
                kill_switch = bool(value)
            else:
                values[record.policy_key] = value
        return values, kill_switch

    def save_risk_policy(self, policy: dict) -> dict:
        portfolio_id = self.ensure_system_portfolio()
        query = select(RiskPolicyRecord).where(
            RiskPolicyRecord.portfolio_id == portfolio_id,
            RiskPolicyRecord.policy_key == policy["key"],
        )
        if self.db.bind and self.db.bind.dialect.name != "sqlite":
            query = query.with_for_update()
        record = self.db.scalar(query)
        if record is None:
            record = RiskPolicyRecord(
                id=_stable_id(portfolio_id, f"policy:{policy['key']}"),
                portfolio_id=portfolio_id,
                policy_key=policy["key"],
                policy_value=policy,
                enabled=True,
                updated_at=utcnow(),
                version_id=1,
            )
            self.db.add(record)
        else:
            record.policy_value = policy
            record.updated_at = utcnow()
        self.db.commit()
        return policy

    def save_kill_switch(self, enabled: bool) -> None:
        portfolio_id = self.ensure_system_portfolio()
        query = select(RiskPolicyRecord).where(
            RiskPolicyRecord.portfolio_id == portfolio_id,
            RiskPolicyRecord.policy_key == "kill_switch",
        )
        if self.db.bind and self.db.bind.dialect.name != "sqlite":
            query = query.with_for_update()
        record = self.db.scalar(query)
        if record is None:
            record = RiskPolicyRecord(
                id=_stable_id(portfolio_id, "policy:kill_switch"),
                portfolio_id=portfolio_id,
                policy_key="kill_switch",
                policy_value={"value": enabled},
                enabled=True,
                updated_at=utcnow(),
                version_id=1,
            )
            self.db.add(record)
        else:
            record.policy_value = {"value": enabled}
            record.updated_at = utcnow()
        self.db.commit()
