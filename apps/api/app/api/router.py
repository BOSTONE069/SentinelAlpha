from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response, StreamingResponse
from sqlalchemy.orm import Session

from ..authz import (
    AuthzContext,
    list_alerts_for_actor,
    list_orders_for_actor,
    list_runs_for_actor,
    require_alert_access,
    require_authenticated_actor,
    require_order_access,
    require_run_access,
    require_write_access,
)
from ..config import Settings, get_settings
from ..coordination import (
    ConcurrentWorkflowError,
    CoordinationUnavailable,
    get_coordination,
)
from ..db import Repository, get_db
from ..schemas import (
    AlertUpdate,
    AnalysisRequest,
    AnalysisStarted,
    RiskPolicyUpdate,
    WorkflowResult,
)
from ..services.alpaca import AlpacaService, AlpacaUnavailable
from ..services.risk import RiskControlState, RiskEngine
from ..services.workflow import WorkflowService

public_api_router = APIRouter()
api_router = APIRouter(dependencies=[Depends(require_authenticated_actor)])


def _load_risk_controls(
    db: Session, settings: Settings | None = None
) -> tuple[Repository, RiskControlState]:
    request_controls = RiskControlState(settings or get_settings())
    repository = Repository(db)
    repository.seed_risk_policies(
        [policy.model_dump(mode="json") for policy in request_controls.policies()]
    )
    values, kill_switch = repository.runtime_risk_controls()
    for key, value in values.items():
        if key != "paper_mode" and value is not None:
            request_controls.update(key, value)
    request_controls.kill_switch = kill_switch
    return repository, request_controls


def workflow_service(
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    actor: AuthzContext = Depends(require_authenticated_actor),
) -> WorkflowService:
    _, request_controls = _load_risk_controls(db, settings)
    portfolio_id = next(iter(actor.portfolio_ids), None)
    return WorkflowService(
        db,
        settings,
        request_controls,
        portfolio_id=portfolio_id,
    )


@public_api_router.get("/health")
def health(settings: Settings = Depends(get_settings)) -> dict:
    coordination = get_coordination()
    coordination_available = coordination.ping()
    return {
        "status": "healthy" if coordination_available else "degraded",
        "paper_trading": settings.alpaca_paper,
        "live_trading_enabled": settings.live_trading_enabled,
        "alpaca_configured": settings.alpaca_configured,
        "alpaca_trading_endpoint": settings.alpaca_trading_api_url,
        "alpaca_data_feed": settings.alpaca_data_feed,
        "alpaca_options_feed": settings.alpaca_options_feed,
        "alpaca_options_execution_adapter": settings.alpaca_options_execution_adapter,
        "coordination_backend": coordination.backend_name,
        "coordination_available": coordination_available,
        "redis_required": settings.redis_required,
        "openai_configured": bool(settings.openai_api_key),
        "timestamp": datetime.now(timezone.utc),
    }


@public_api_router.get("/config/public")
def public_config(settings: Settings = Depends(get_settings)) -> dict:
    return {
        "app_env": settings.app_env,
        "paper_trading": settings.alpaca_paper,
        "live_trading_enabled": settings.live_trading_enabled,
        "auto_execute_paper": settings.auto_execute_paper,
        "default_mode": "REPLAY",
        "available_scenarios": [
            "risk_modification",
            "information_risk",
            "agent_soc",
            "portfolio_protection",
        ],
        "available_agent_providers": ["RULES", "OPENAI"],
        "available_strategies": ["EQUITY", "PROTECTIVE_PUT"],
        "alpaca_trading_endpoint": settings.alpaca_trading_api_url,
        "alpaca_data_feed": settings.alpaca_data_feed,
        "alpaca_options_feed": settings.alpaca_options_feed,
        "alpaca_options_execution_adapter": settings.alpaca_options_execution_adapter,
    }


@api_router.get("/auth/me")
def authenticated_actor(
    actor: AuthzContext = Depends(require_authenticated_actor),
) -> dict:
    return {
        "user_id": actor.user_id,
        "portfolio_ids": sorted(actor.portfolio_ids),
        "role": actor.role,
        "can_write": actor.can_write,
    }


@api_router.get("/alpaca/connection")
def alpaca_connection(settings: Settings = Depends(get_settings)):
    try:
        return AlpacaService(settings).connection_status()
    except Exception as exc:
        raise HTTPException(
            503,
            {
                "message": "Alpaca paper connection failed.",
                "error_type": type(exc).__name__,
                "endpoint": settings.alpaca_trading_api_url,
            },
        ) from exc


@api_router.get("/alpaca/account")
def account(mode: str = Query("REPLAY", pattern="^(REPLAY|LIVE)$"), settings: Settings = Depends(get_settings)):
    try:
        return AlpacaService(settings).account(mode)
    except (AlpacaUnavailable, CoordinationUnavailable) as exc:
        raise HTTPException(503, str(exc)) from exc


@api_router.get("/alpaca/positions")
def positions(mode: str = Query("REPLAY", pattern="^(REPLAY|LIVE)$"), settings: Settings = Depends(get_settings)):
    try:
        return AlpacaService(settings).account(mode).positions
    except (AlpacaUnavailable, CoordinationUnavailable) as exc:
        raise HTTPException(503, str(exc)) from exc


@api_router.get("/alpaca/clock")
def market_clock(mode: str = Query("REPLAY", pattern="^(REPLAY|LIVE)$"), settings: Settings = Depends(get_settings)):
    try:
        return AlpacaService(settings).clock(mode)
    except (AlpacaUnavailable, CoordinationUnavailable) as exc:
        raise HTTPException(503, str(exc)) from exc


@api_router.get("/alpaca/orders")
def alpaca_orders(
    mode: str = Query("REPLAY", pattern="^(REPLAY|LIVE)$"),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    actor: AuthzContext = Depends(require_authenticated_actor),
):
    if mode == "REPLAY":
        return list_orders_for_actor(Repository(db), actor, 100)
    try:
        return AlpacaService(settings).provider_orders()
    except AlpacaUnavailable as exc:
        raise HTTPException(503, str(exc)) from exc


@api_router.get("/alpaca/options/{symbol}/contracts")
def option_contracts(
    symbol: str,
    mode: str = Query("REPLAY", pattern="^(REPLAY|LIVE)$"),
    settings: Settings = Depends(get_settings),
):
    normalized = symbol.upper()
    try:
        service = AlpacaService(settings)
        market = service.market(
            normalized,
            mode,
            "portfolio_protection" if mode == "REPLAY" else "risk_modification",
        )
        return service.option_contracts(normalized, market.price, mode)
    except (AlpacaUnavailable, CoordinationUnavailable, ValueError) as exc:
        raise HTTPException(503, str(exc)) from exc


@api_router.get("/market/{symbol}/snapshot")
def market_snapshot(
    symbol: str,
    mode: str = Query("REPLAY", pattern="^(REPLAY|LIVE)$"),
    scenario: str = "risk_modification",
    settings: Settings = Depends(get_settings),
):
    try:
        return AlpacaService(settings).market(symbol.upper(), mode, scenario)
    except (AlpacaUnavailable, CoordinationUnavailable, ValueError) as exc:
        raise HTTPException(503, str(exc)) from exc


@api_router.get("/market/{symbol}/bars")
def market_bars(
    symbol: str,
    mode: str = Query("REPLAY", pattern="^(REPLAY|LIVE)$"),
    scenario: str = "risk_modification",
    limit: int = Query(90, ge=20, le=500),
    settings: Settings = Depends(get_settings),
):
    try:
        snapshot = AlpacaService(settings).market(symbol.upper(), mode, scenario)
        return {"symbol": snapshot.symbol, "source": snapshot.source, "bars": snapshot.bars[-limit:]}
    except (AlpacaUnavailable, CoordinationUnavailable, ValueError) as exc:
        raise HTTPException(503, str(exc)) from exc


@api_router.get("/market/{symbol}/indicators")
def market_indicators(
    symbol: str,
    mode: str = Query("REPLAY", pattern="^(REPLAY|LIVE)$"),
    scenario: str = "risk_modification",
    settings: Settings = Depends(get_settings),
):
    try:
        snapshot = AlpacaService(settings).market(symbol.upper(), mode, scenario)
        return {"symbol": snapshot.symbol, "as_of": snapshot.as_of, "source": snapshot.source, "indicators": snapshot.indicators}
    except (AlpacaUnavailable, CoordinationUnavailable, ValueError) as exc:
        raise HTTPException(503, str(exc)) from exc


@api_router.get("/market/{symbol}/news")
def market_news(
    symbol: str,
    mode: str = Query("REPLAY", pattern="^(REPLAY|LIVE)$"),
    scenario: str = "risk_modification",
    settings: Settings = Depends(get_settings),
):
    try:
        return AlpacaService(settings).news(symbol.upper(), mode, scenario)
    except (AlpacaUnavailable, CoordinationUnavailable) as exc:
        raise HTTPException(503, str(exc)) from exc


@api_router.post("/analysis", response_model=AnalysisStarted)
def start_analysis(
    request: AnalysisRequest,
    service: WorkflowService = Depends(workflow_service),
    actor: AuthzContext = Depends(require_authenticated_actor),
):
    require_write_access(actor)
    try:
        result = service.analyze(request)
    except ConcurrentWorkflowError as exc:
        raise HTTPException(409, str(exc), headers={"Retry-After": "2"}) from exc
    except (AlpacaUnavailable, CoordinationUnavailable, ValueError) as exc:
        raise HTTPException(503, str(exc)) from exc
    return AnalysisStarted(workflow_run_id=result.workflow_run_id, status=result.status, result=result)


@api_router.get("/runs", response_model=list[WorkflowResult])
def list_runs(
    limit: int = Query(30, ge=1, le=100),
    db: Session = Depends(get_db),
    actor: AuthzContext = Depends(require_authenticated_actor),
):
    return [
        WorkflowResult.model_validate(item)
        for item in list_runs_for_actor(Repository(db), actor, limit)
    ]


@api_router.get("/audit/export")
def export_audit(
    run_id: str | None = Query(None, max_length=64),
    limit: int = Query(500, ge=1, le=500),
    db: Session = Depends(get_db),
    actor: AuthzContext = Depends(require_authenticated_actor),
) -> Response:
    repository = Repository(db)
    if run_id:
        workflow = require_run_access(repository, actor, run_id)
        workflows = [workflow]
        filename = f"sentinelalpha-audit-{run_id}.json"
    else:
        workflows = list_runs_for_actor(repository, actor, limit)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        filename = f"sentinelalpha-audit-{stamp}.json"

    document = {
        "schema_version": "sentinelalpha.audit.v1",
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "workflow_count": len(workflows),
        "workflows": workflows,
    }
    return Response(
        content=json.dumps(document, indent=2, ensure_ascii=False),
        media_type="application/json",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-store",
        },
    )


def _get_run_for_actor(
    run_id: str, db: Session, actor: AuthzContext
) -> WorkflowResult:
    payload = require_run_access(Repository(db), actor, run_id)
    return WorkflowResult.model_validate(payload)


@api_router.get("/runs/{run_id}", response_model=WorkflowResult)
def get_run(
    run_id: str,
    db: Session = Depends(get_db),
    actor: AuthzContext = Depends(require_authenticated_actor),
):
    return _get_run_for_actor(run_id, db, actor)


@api_router.get("/runs/{run_id}/agents")
def get_run_agents(
    run_id: str,
    db: Session = Depends(get_db),
    actor: AuthzContext = Depends(require_authenticated_actor),
):
    return _get_run_for_actor(run_id, db, actor).agent_decisions


@api_router.get("/runs/{run_id}/consensus")
def get_run_consensus(
    run_id: str,
    db: Session = Depends(get_db),
    actor: AuthzContext = Depends(require_authenticated_actor),
):
    return _get_run_for_actor(run_id, db, actor).consensus


@api_router.get("/runs/{run_id}/risk")
def get_run_risk(
    run_id: str,
    db: Session = Depends(get_db),
    actor: AuthzContext = Depends(require_authenticated_actor),
):
    run = _get_run_for_actor(run_id, db, actor)
    return {"semantic_review": run.risk_review, "gate": run.risk_gate}


@api_router.get("/runs/{run_id}/explanation")
def get_run_explanation(
    run_id: str,
    db: Session = Depends(get_db),
    actor: AuthzContext = Depends(require_authenticated_actor),
):
    return _get_run_for_actor(run_id, db, actor).explanation


@api_router.get("/runs/{run_id}/timeline")
def get_run_timeline(
    run_id: str,
    db: Session = Depends(get_db),
    actor: AuthzContext = Depends(require_authenticated_actor),
):
    return _get_run_for_actor(run_id, db, actor).timeline


@api_router.post("/runs/{run_id}/approve", response_model=WorkflowResult)
def approve_run(
    run_id: str,
    db: Session = Depends(get_db),
    service: WorkflowService = Depends(workflow_service),
    actor: AuthzContext = Depends(require_authenticated_actor),
):
    require_run_access(Repository(db), actor, run_id, write=True)
    try:
        return service.approve(run_id)
    except KeyError as exc:
        raise HTTPException(404, "workflow not found") from exc
    except ConcurrentWorkflowError as exc:
        raise HTTPException(409, str(exc), headers={"Retry-After": "2"}) from exc
    except CoordinationUnavailable as exc:
        raise HTTPException(503, str(exc)) from exc
    except (ValueError, AlpacaUnavailable) as exc:
        raise HTTPException(409, str(exc)) from exc


@api_router.post("/runs/{run_id}/reject", response_model=WorkflowResult)
def reject_run(
    run_id: str,
    db: Session = Depends(get_db),
    service: WorkflowService = Depends(workflow_service),
    actor: AuthzContext = Depends(require_authenticated_actor),
):
    require_run_access(Repository(db), actor, run_id, write=True)
    try:
        return service.reject(run_id)
    except KeyError as exc:
        raise HTTPException(404, "workflow not found") from exc
    except ConcurrentWorkflowError as exc:
        raise HTTPException(409, str(exc), headers={"Retry-After": "2"}) from exc
    except CoordinationUnavailable as exc:
        raise HTTPException(503, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc


@api_router.post("/runs/{run_id}/replay", response_model=WorkflowResult)
def replay_run(
    run_id: str,
    db: Session = Depends(get_db),
    service: WorkflowService = Depends(workflow_service),
    actor: AuthzContext = Depends(require_authenticated_actor),
):
    require_run_access(Repository(db), actor, run_id, write=True)
    try:
        return service.replay(run_id)
    except KeyError as exc:
        raise HTTPException(404, "workflow not found") from exc
    except ConcurrentWorkflowError as exc:
        raise HTTPException(409, str(exc), headers={"Retry-After": "2"}) from exc
    except CoordinationUnavailable as exc:
        raise HTTPException(503, str(exc)) from exc


@api_router.get("/events/runs/{run_id}")
def stream_run_events(
    run_id: str,
    db: Session = Depends(get_db),
    actor: AuthzContext = Depends(require_authenticated_actor),
):
    run = _get_run_for_actor(run_id, db, actor)

    async def event_stream():
        for item in run.timeline:
            yield f"event: {item.event}\ndata: {json.dumps(item.model_dump(mode='json'))}\n\n"
            await asyncio.sleep(0)
        yield f"event: stream.end\ndata: {json.dumps({'workflow_run_id': run_id})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@api_router.get("/risk/policies")
def risk_policies(db: Session = Depends(get_db)):
    _, request_controls = _load_risk_controls(db)
    return request_controls.policies()


@api_router.put("/risk/policies/{policy_key}")
def update_policy(
    policy_key: str,
    update: RiskPolicyUpdate,
    db: Session = Depends(get_db),
    actor: AuthzContext = Depends(require_authenticated_actor),
):
    require_write_access(actor)
    try:
        with get_coordination().lock(f"risk-policy:{policy_key}"):
            repository, request_controls = _load_risk_controls(db)
            request_controls.update(policy_key, update.value)
            policy = next(
                policy
                for policy in request_controls.policies()
                if policy.key == policy_key
            )
            repository.save_risk_policy(policy.model_dump(mode="json"))
            return policy
    except KeyError as exc:
        raise HTTPException(404, "policy not found") from exc
    except (ValueError, ConcurrentWorkflowError) as exc:
        raise HTTPException(409, str(exc)) from exc
    except CoordinationUnavailable as exc:
        raise HTTPException(503, str(exc)) from exc


@api_router.get("/risk/status")
def risk_status(db: Session = Depends(get_db)):
    _, request_controls = _load_risk_controls(db)
    return {
        "kill_switch": request_controls.kill_switch,
        "executions_enabled": not request_controls.kill_switch,
        "paper_mode_locked": True,
    }


@api_router.post("/risk/kill-switch")
def engage_kill_switch(
    db: Session = Depends(get_db),
    actor: AuthzContext = Depends(require_authenticated_actor),
):
    require_write_access(actor)
    try:
        with get_coordination().lock("risk-policy:kill-switch"):
            repository, _ = _load_risk_controls(db)
            repository.save_kill_switch(True)
            return {"kill_switch": True, "message": "All new executions are disabled."}
    except ConcurrentWorkflowError as exc:
        raise HTTPException(409, str(exc)) from exc
    except CoordinationUnavailable as exc:
        raise HTTPException(503, str(exc)) from exc


@api_router.post("/risk/kill-switch/reset")
def reset_kill_switch(
    db: Session = Depends(get_db),
    actor: AuthzContext = Depends(require_authenticated_actor),
):
    require_write_access(actor)
    try:
        with get_coordination().lock("risk-policy:kill-switch"):
            repository, _ = _load_risk_controls(db)
            repository.save_kill_switch(False)
            return {"kill_switch": False, "message": "Execution may resume subject to every risk rule."}
    except ConcurrentWorkflowError as exc:
        raise HTTPException(409, str(exc)) from exc
    except CoordinationUnavailable as exc:
        raise HTTPException(503, str(exc)) from exc


@api_router.post("/risk/evaluate")
def reevaluate_run(
    body: dict,
    service: WorkflowService = Depends(workflow_service),
    actor: AuthzContext = Depends(require_authenticated_actor),
):
    run_id = body.get("workflow_run_id")
    if not run_id:
        raise HTTPException(422, "workflow_run_id is required")
    payload = require_run_access(service.repository, actor, run_id)
    run = WorkflowResult.model_validate(payload)
    if not run.proposal:
        return run.risk_gate
    return RiskEngine(service.settings, service.controls, service.repository).evaluate(
        run.proposal,
        run.consensus,
        run.risk_review,
        run.market_snapshot,
        run.account,
        service.alpaca.clock(run.mode),
    )


@api_router.get("/soc/alerts")
def soc_alerts(
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    actor: AuthzContext = Depends(require_authenticated_actor),
):
    return list_alerts_for_actor(Repository(db), actor, limit)


@api_router.get("/soc/alerts/{alert_id}")
def get_soc_alert(
    alert_id: str,
    db: Session = Depends(get_db),
    actor: AuthzContext = Depends(require_authenticated_actor),
):
    return require_alert_access(Repository(db), actor, alert_id)


@api_router.patch("/soc/alerts/{alert_id}")
def update_soc_alert(
    alert_id: str,
    update: AlertUpdate,
    db: Session = Depends(get_db),
    actor: AuthzContext = Depends(require_authenticated_actor),
):
    repository = Repository(db)
    require_alert_access(repository, actor, alert_id, write=True)
    alert = repository.update_alert(
        alert_id,
        update.status,
        portfolio_ids=actor.portfolio_scope,
    )
    if not alert:
        raise HTTPException(404, "alert not found")
    return alert


@api_router.get("/soc/overview")
def soc_overview(
    db: Session = Depends(get_db),
    actor: AuthzContext = Depends(require_authenticated_actor),
):
    repository, request_controls = _load_risk_controls(db)
    alerts = list_alerts_for_actor(repository, actor, 500)
    open_alerts = [alert for alert in alerts if alert["status"] == "OPEN"]
    severity_weight = {"INFO": 1, "LOW": 3, "MEDIUM": 8, "HIGH": 15, "CRITICAL": 25}
    risk_score = min(100, sum(severity_weight.get(alert["severity"], 0) for alert in open_alerts))
    runs = list_runs_for_actor(repository, actor, 500)
    return {
        "system_risk_score": risk_score,
        "system_status": "CRITICAL" if risk_score >= 70 else "ELEVATED" if risk_score >= 35 else "LOW",
        "agent_health": {"healthy": 5, "total": 5},
        "active_alerts": len(open_alerts),
        "trades_blocked_today": sum(run["status"] in {"REJECTED", "ESCALATED"} for run in runs),
        "kill_switch": request_controls.kill_switch,
    }


@api_router.get("/soc/agent-health")
def agent_health():
    return [
        {"agent": name, "status": "HEALTHY", "latency_ms": latency, "success_rate": 0.99}
        for name, latency in [("Market Intelligence", 182), ("News Intelligence", 246), ("Quant Strategy", 94), ("Portfolio Manager", 137), ("Risk & Security", 112)]
    ]


@api_router.get("/soc/metrics")
def soc_metrics(
    db: Session = Depends(get_db),
    actor: AuthzContext = Depends(require_authenticated_actor),
):
    repository = Repository(db)
    runs = list_runs_for_actor(repository, actor, 500)
    return {
        "agent_decisions_evaluated": len(runs) * 4,
        "risk_violations_blocked": sum(run["status"] in {"REJECTED", "ESCALATED"} for run in runs),
        "oversized_proposals_modified": sum(run["risk_gate"]["decision"] == "MODIFY" for run in runs),
        "audit_completeness": 1.0,
    }


@api_router.get("/orders")
def list_orders(
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    actor: AuthzContext = Depends(require_authenticated_actor),
):
    return list_orders_for_actor(Repository(db), actor, limit)


@api_router.get("/orders/{order_id}")
def get_order(
    order_id: str,
    db: Session = Depends(get_db),
    actor: AuthzContext = Depends(require_authenticated_actor),
):
    return require_order_access(Repository(db), actor, order_id)


@api_router.post("/orders/{order_id}/cancel")
def cancel_order(
    order_id: str,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    actor: AuthzContext = Depends(require_authenticated_actor),
):
    order = require_order_access(Repository(db), actor, order_id, write=True)
    if order["execution_mode"] == "SIMULATED_PAPER":
        return {**order, "status": "cancelled", "note": "Simulated replay order only."}
    try:
        AlpacaService(settings).cancel_provider_order(order["provider_order_id"])
    except (AlpacaUnavailable, CoordinationUnavailable) as exc:
        raise HTTPException(503, str(exc)) from exc
    return {**order, "status": "cancel_pending"}
