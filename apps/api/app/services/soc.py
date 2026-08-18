from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from ..schemas import (
    AgentDecision,
    ConsensusDecision,
    MarketSnapshot,
    RiskGateResult,
    SocAlert,
    TradeProposal,
)


def _alert(
    rule_id: str,
    alert_type: str,
    severity: str,
    title: str,
    detail: str,
    symbol: str,
    run_id: str,
) -> SocAlert:
    return SocAlert(
        id=f"alert-{uuid4().hex[:12]}",
        rule_id=rule_id,
        alert_type=alert_type,
        severity=severity,
        title=title,
        detail=detail,
        symbol=symbol,
        workflow_run_id=run_id,
        created_at=datetime.now(timezone.utc),
    )


def run_soc_checks(
    run_id: str,
    symbol: str,
    scenario: str,
    consensus: ConsensusDecision,
    proposal: TradeProposal | None,
    gate: RiskGateResult,
    market: MarketSnapshot,
    decisions: list[AgentDecision],
    max_new_position_pct: float,
    max_data_age_seconds: int,
) -> list[SocAlert]:
    alerts: list[SocAlert] = []
    if consensus.disagreement_score > 0.60:
        alerts.append(_alert("SOC001", "AGENT_DISAGREEMENT", "MEDIUM", "Agent disagreement elevated", f"Council disagreement reached {consensus.disagreement_score:.0%}.", symbol, run_id))
    if proposal and proposal.consensus_confidence < 0.70:
        alerts.append(_alert("SOC002", "LOW_CONFIDENCE_TRADE", "HIGH", "Low-confidence execution attempt", f"A {proposal.side} intent was produced at {proposal.consensus_confidence:.0%} confidence.", symbol, run_id))
    if proposal and proposal.requested_position_pct > 2 * max_new_position_pct:
        alerts.append(_alert("SOC003", "POSITION_LIMIT_ATTEMPT", "HIGH", "Oversized position proposed", f"Requested {proposal.requested_position_pct:.1%}, over twice the per-workflow limit.", symbol, run_id))
    age = (datetime.now(timezone.utc) - market.as_of).total_seconds()
    if age > max_data_age_seconds:
        alerts.append(_alert("SOC005", "STALE_DATA", "CRITICAL", "Stale market input blocked", f"Snapshot age {age:.0f}s exceeded the {max_data_age_seconds}s policy.", symbol, run_id))
    if any("sentiment_spike" in decision.risk_flags for decision in decisions):
        alerts.append(_alert("SOC006", "NEWS_SENTIMENT_ANOMALY", "MEDIUM", "News sentiment anomaly", "A sharp narrative change lacks broad corroboration; this is an information-risk signal.", symbol, run_id))
    if any(decision.latency_ms > 5000 for decision in decisions):
        alerts.append(_alert("SOC007", "AGENT_LATENCY_ANOMALY", "LOW", "Agent latency outside baseline", "One analytical agent exceeded the configured response-time baseline.", symbol, run_id))
    if gate.decision == "MODIFY":
        alerts.append(_alert("SOC003", "POSITION_LIMIT_ATTEMPT", "HIGH", "Risk gate reduced proposed exposure", f"Deterministic policy changed {gate.requested_position_pct:.1%} to {gate.approved_position_pct:.1%}.", symbol, run_id))
    if scenario == "agent_soc":
        alerts.extend(
            [
                _alert("SOC004", "REPEATED_REJECTION", "MEDIUM", "Repeated rejected proposals", "Three rejected intents for this symbol were observed inside the replay window.", symbol, run_id),
                _alert("SOC008", "TOOL_INVOCATION_ANOMALY", "HIGH", "Tool invocation burst", "The market agent repeated the same data request eight times inside one workflow.", symbol, run_id),
                _alert("SOC009", "DUPLICATE_TRADE_INTENT", "HIGH", "Duplicate trade intent", "Concurrent workflows attempted the same symbol and direction.", symbol, run_id),
            ]
        )
    deduped: dict[str, SocAlert] = {}
    for alert in alerts:
        deduped[f"{alert.rule_id}:{alert.alert_type}"] = alert
    return list(deduped.values())
