from dataclasses import replace
from datetime import datetime, timezone

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.authz import (
    AuthzContext,
    list_alerts_for_actor,
    list_orders_for_actor,
    list_runs_for_actor,
    require_alert_access,
    require_order_access,
    require_run_access,
)
from app.config import get_settings
from app.coordination import CoordinationBackend
from app.db import (
    Base,
    PortfolioRecord,
    Repository,
    SYSTEM_PORTFOLIO_ID,
    SYSTEM_USER_ID,
    UserRecord,
    WorkflowRecord,
)
from app.schemas import AnalysisRequest
from app.services.risk import RiskControlState
from app.services.workflow import WorkflowService


OTHER_USER_ID = "00000000-0000-0000-0000-000000000101"
OTHER_PORTFOLIO_ID = "00000000-0000-0000-0000-000000000102"


def _actor(portfolio_id: str, role: str = "operator") -> AuthzContext:
    return AuthzContext(
        user_id=SYSTEM_USER_ID if portfolio_id == SYSTEM_PORTFOLIO_ID else OTHER_USER_ID,
        portfolio_ids=frozenset({portfolio_id}),
        role=role,
    )


def _assert_status(status_code: int, callback) -> None:
    with pytest.raises(HTTPException) as rejected:
        callback()
    assert rejected.value.status_code == status_code


def test_run_order_and_alert_access_is_portfolio_scoped():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    settings = replace(get_settings(), redis_url=None)
    coordination = CoordinationBackend(settings)

    with sessionmaker(bind=engine, expire_on_commit=False)() as session:
        service = WorkflowService(
            session,
            settings,
            RiskControlState(settings),
            coordination,
        )
        owner_order_run = service.analyze(AnalysisRequest(symbol="AAPL"))
        owner_order_run = service.approve(owner_order_run.workflow_run_id)
        other_order_run = service.analyze(AnalysisRequest(symbol="MSFT"))
        other_order_run = service.approve(other_order_run.workflow_run_id)
        owner_alert_run = service.analyze(
            AnalysisRequest(symbol="NVDA", scenario="agent_soc")
        )
        other_alert_run = service.analyze(
            AnalysisRequest(symbol="TSLA", scenario="agent_soc")
        )

        session.add(
            UserRecord(
                id=OTHER_USER_ID,
                email="other@example.test",
                display_name="Other operator",
                created_at=datetime.now(timezone.utc),
            )
        )
        session.add(
            PortfolioRecord(
                id=OTHER_PORTFOLIO_ID,
                user_id=OTHER_USER_ID,
                name="Other portfolio",
                provider="alpaca",
                environment="paper",
                created_at=datetime.now(timezone.utc),
            )
        )
        session.flush()
        for run_id in (
            other_order_run.workflow_run_id,
            other_alert_run.workflow_run_id,
        ):
            session.get(WorkflowRecord, run_id).portfolio_id = OTHER_PORTFOLIO_ID
        session.commit()

        repository = Repository(session, coordination)
        owner = _actor(SYSTEM_PORTFOLIO_ID)
        outsider = _actor(OTHER_PORTFOLIO_ID)
        viewer = _actor(SYSTEM_PORTFOLIO_ID, "viewer")
        owner_order_id = owner_order_run.execution.id
        other_order_id = other_order_run.execution.id
        owner_alert_id = owner_alert_run.soc_alerts[0].id
        other_alert_id = other_alert_run.soc_alerts[0].id

        assert require_run_access(
            repository, owner, owner_order_run.workflow_run_id
        )["workflow_run_id"] == owner_order_run.workflow_run_id
        assert require_order_access(repository, owner, owner_order_id)["id"] == owner_order_id
        assert require_alert_access(repository, owner, owner_alert_id)["id"] == owner_alert_id

        _assert_status(
            404,
            lambda: require_run_access(
                repository, owner, other_order_run.workflow_run_id
            ),
        )
        _assert_status(
            404, lambda: require_order_access(repository, owner, other_order_id)
        )
        _assert_status(
            404, lambda: require_alert_access(repository, owner, other_alert_id)
        )

        assert require_run_access(
            repository, outsider, other_order_run.workflow_run_id
        )
        assert require_order_access(repository, outsider, other_order_id)
        assert require_alert_access(repository, outsider, other_alert_id)

        _assert_status(
            403,
            lambda: require_run_access(
                repository, viewer, owner_order_run.workflow_run_id, write=True
            ),
        )
        _assert_status(
            403,
            lambda: require_order_access(
                repository, viewer, owner_order_id, write=True
            ),
        )
        _assert_status(
            403,
            lambda: require_alert_access(
                repository, viewer, owner_alert_id, write=True
            ),
        )

        assert {
            run["workflow_run_id"] for run in list_runs_for_actor(repository, owner, 20)
        }.isdisjoint(
            {other_order_run.workflow_run_id, other_alert_run.workflow_run_id}
        )
        assert {order["id"] for order in list_orders_for_actor(repository, owner, 20)} == {
            owner_order_id
        }
        assert other_alert_id not in {
            alert["id"] for alert in list_alerts_for_actor(repository, owner, 50)
        }
