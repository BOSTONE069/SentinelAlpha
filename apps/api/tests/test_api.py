import json
from dataclasses import replace

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.api.router import export_audit, health, public_config, start_analysis
from app.authz import (
    AuthzContext,
    require_authenticated_actor,
    validate_auth_configuration,
)
from app.config import get_settings
from app.db import Base, SYSTEM_PORTFOLIO_ID, SYSTEM_USER_ID
from app.main import app
from app.schemas import AnalysisRequest
from app.services.risk import RiskControlState
from app.services.workflow import WorkflowService


OPERATOR = AuthzContext(
    user_id=SYSTEM_USER_ID,
    portfolio_ids=frozenset({SYSTEM_PORTFOLIO_ID}),
    role="operator",
)


def test_minimum_http_contract_is_registered():
    paths = set(app.openapi()["paths"])
    assert {
        "/api/v1/health",
        "/api/v1/alpaca/account",
        "/api/v1/alpaca/connection",
        "/api/v1/alpaca/positions",
        "/api/v1/alpaca/options/{symbol}/contracts",
        "/api/v1/market/{symbol}/bars",
        "/api/v1/market/{symbol}/news",
        "/api/v1/analysis",
        "/api/v1/audit/export",
        "/api/v1/runs/{run_id}",
        "/api/v1/soc/overview",
        "/api/v1/soc/alerts",
        "/api/v1/orders",
    } <= paths


def test_health_contract_keeps_live_money_disabled():
    settings = get_settings()
    response = health(settings)
    config = public_config(settings)
    assert response["status"] == "healthy"
    assert response["paper_trading"] is True
    assert response["live_trading_enabled"] is False
    assert response["alpaca_trading_endpoint"] == "https://paper-api.alpaca.markets/v2"
    assert config["live_trading_enabled"] is False


def test_analysis_endpoint_contract_returns_auditable_result():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with sessionmaker(bind=engine, expire_on_commit=False)() as session:
        settings = get_settings()
        service = WorkflowService(session, settings, RiskControlState(settings))
        response = start_analysis(AnalysisRequest(symbol="AAPL"), service, OPERATOR)
        assert response.workflow_run_id == response.result.workflow_run_id
        assert response.result.risk_gate.decision == "MODIFY"
        assert response.result.timeline


def test_audit_export_download_contains_complete_workflow():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with sessionmaker(bind=engine, expire_on_commit=False)() as session:
        settings = get_settings()
        service = WorkflowService(session, settings, RiskControlState(settings))
        workflow = service.analyze(AnalysisRequest(symbol="AAPL"))

        response = export_audit(workflow.workflow_run_id, 500, session, OPERATOR)
        document = json.loads(response.body)

        assert response.media_type == "application/json"
        assert response.headers["content-disposition"].startswith("attachment;")
        assert document["schema_version"] == "sentinelalpha.audit.v1"
        assert document["workflow_count"] == 1
        assert document["workflows"][0]["workflow_run_id"] == workflow.workflow_run_id
        assert document["workflows"][0]["timeline"]


def test_operational_routes_require_bearer_authentication():
    schema = app.openapi()
    assert schema["paths"]["/api/v1/health"]["get"].get("security") is None
    for method, path in [
        ("get", "/api/v1/runs"),
        ("get", "/api/v1/runs/{run_id}"),
        ("post", "/api/v1/runs/{run_id}/approve"),
        ("get", "/api/v1/orders"),
        ("post", "/api/v1/orders/{order_id}/cancel"),
        ("get", "/api/v1/soc/alerts"),
        ("patch", "/api/v1/soc/alerts/{alert_id}"),
    ]:
        assert schema["paths"][path][method]["security"] == [
            {"SentinelAlpha bearer token": []}
        ]

    with pytest.raises(HTTPException) as anonymous:
        require_authenticated_actor(None, get_settings())
    assert anonymous.value.status_code == 401
    assert anonymous.value.headers == {"WWW-Authenticate": "Bearer"}


def test_bearer_token_establishes_configured_actor():
    settings = replace(
        get_settings(),
        api_auth_token="correct-token",
        api_auth_role="viewer",
        api_auth_user_id="user-2",
        api_auth_portfolio_id="portfolio-2",
    )
    credentials = HTTPAuthorizationCredentials(
        scheme="Bearer", credentials="correct-token"
    )
    actor = require_authenticated_actor(credentials, settings)
    assert actor.user_id == "user-2"
    assert actor.portfolio_ids == frozenset({"portfolio-2"})
    assert actor.role == "viewer"
    assert actor.can_write is False

    with pytest.raises(HTTPException) as rejected:
        require_authenticated_actor(
            HTTPAuthorizationCredentials(scheme="Bearer", credentials="wrong"),
            settings,
        )
    assert rejected.value.status_code == 401


def test_production_refuses_missing_or_weak_authentication_token():
    settings = get_settings()
    for token in (None, "too-short"):
        with pytest.raises(RuntimeError, match="at least 32 characters"):
            validate_auth_configuration(
                replace(settings, app_env="production", api_auth_token=token)
            )
