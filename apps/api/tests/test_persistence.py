from dataclasses import replace

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from app import db as db_module
from app.config import get_settings
from app.coordination import ConcurrentWorkflowError, CoordinationBackend
from app.db import (
    AgentDecisionRecord,
    AuditEventRecord,
    Base,
    MarketSnapshotRecord,
    Repository,
    RiskCheckRecord,
    RiskPolicyRecord,
    WorkflowRecord,
)
from app.schemas import AnalysisRequest, WorkflowResult
from app.services.risk import RiskControlState
from app.services.workflow import WorkflowService


def _database():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)()


def test_workflow_is_normalized_and_reconstructed_without_document_blob():
    settings = get_settings()
    coordination = CoordinationBackend(replace(settings, redis_url=None))
    with _database() as session:
        service = WorkflowService(
            session, settings, RiskControlState(settings), coordination
        )
        result = service.analyze(AnalysisRequest(symbol="AAPL"))

        workflow = session.get(WorkflowRecord, result.workflow_run_id)
        assert workflow is not None
        assert workflow.legacy_data is None
        assert session.scalar(select(func.count(MarketSnapshotRecord.id))) == 1
        assert session.scalar(select(func.count(AgentDecisionRecord.id))) == 4
        assert session.scalar(select(func.count(RiskCheckRecord.id))) == 14
        assert session.scalar(select(func.count(AuditEventRecord.id))) >= 10

        restored = WorkflowResult.model_validate(
            service.repository.get_workflow(result.workflow_run_id)
        )
        assert restored == result

        legacy_payload = result.model_dump(mode="json")
        legacy_payload["replay_of"] = "missing-legacy-parent"
        service.repository.save_workflow(legacy_payload)
        assert session.get(WorkflowRecord, result.workflow_run_id).replay_of is None


def test_local_concurrency_fallback_rejects_conflicting_workflow():
    settings = replace(get_settings(), redis_url=None)
    coordination = CoordinationBackend(settings)

    with coordination.lock("analysis:replay:AAPL"):
        with pytest.raises(ConcurrentWorkflowError, match="already running"):
            with coordination.lock("analysis:replay:AAPL"):
                pass


def test_risk_policy_updates_are_persisted():
    settings = get_settings()
    controls = RiskControlState(settings)
    with _database() as session:
        repository = Repository(
            session, CoordinationBackend(replace(settings, redis_url=None))
        )
        repository.seed_risk_policies(
            [policy.model_dump(mode="json") for policy in controls.policies()]
        )
        policy = next(
            policy
            for policy in controls.policies()
            if policy.key == "max_trades_per_day"
        )
        updated = policy.model_copy(update={"value": 7})
        repository.save_risk_policy(updated.model_dump(mode="json"))

        values, kill_switch = repository.runtime_risk_controls()
        assert values["max_trades_per_day"] == 7
        assert kill_switch is False
        # Global defaults plus one portfolio-scoped override.
        assert session.scalar(select(func.count(RiskPolicyRecord.id))) == len(
            controls.policies()
        ) + 1


def test_postgres_migrations_use_an_owned_transaction_and_transaction_lock(
    monkeypatch,
):
    events: list[str] = []

    class FakeConnection:
        dialect = type("Dialect", (), {"name": "postgresql"})()

        def execute(self, statement, parameters):
            events.append("lock")
            assert str(statement) == "SELECT pg_advisory_xact_lock(:key)"
            assert parameters == {"key": 7_309_861_047_251}

    connection = FakeConnection()

    class Transaction:
        def __enter__(self):
            events.append("begin")
            return connection

        def __exit__(self, exc_type, exc, traceback):
            events.append("commit" if exc_type is None else "rollback")
            return False

    class FakeEngine:
        def begin(self):
            return Transaction()

    def upgrade(config, revision):
        assert config.attributes["connection"] is connection
        assert revision == "head"
        events.append("upgrade")

    monkeypatch.setattr(db_module, "engine", FakeEngine())
    monkeypatch.setattr("alembic.command.upgrade", upgrade)

    db_module.run_migrations()

    assert events == ["begin", "lock", "upgrade", "commit"]
