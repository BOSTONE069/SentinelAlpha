from __future__ import annotations

from ..schemas import (
    AgentDecision,
    ConsensusDecision,
    DecisionExplanation,
    ExecutionOrder,
    HedgePlan,
    RiskGateResult,
    TradeProposal,
)


def build_explanation(
    symbol: str,
    decisions: list[AgentDecision],
    consensus: ConsensusDecision,
    proposal: TradeProposal | None,
    gate: RiskGateResult,
    execution: ExecutionOrder | None = None,
) -> DecisionExplanation:
    positive = list(dict.fromkeys(factor for decision in decisions for factor in decision.bullish_factors))[:6]
    negative = list(dict.fromkeys(factor for decision in decisions for factor in decision.bearish_factors))[:6]
    invalidation = list(
        dict.fromkeys(condition for decision in decisions for condition in decision.invalidation_conditions)
    )[:6]
    action = consensus.direction
    if gate.decision in {"REJECT", "ESCALATE"}:
        headline = f"{symbol} {action} proposal — {gate.decision.lower()}ed"
    elif gate.decision == "MODIFY":
        headline = f"{symbol} {action} approved at a policy-reduced size"
    else:
        headline = f"{symbol} {action} passed the supervisory gate"

    agreeing = ", ".join(consensus.supporting_agents) or "no analytical agents"
    summary = (
        f"The council produced a {action} opinion at {consensus.confidence:.0%} confidence. "
        f"{consensus.agreeing_agents} of {consensus.total_agents} agents agreed. "
        f"The deterministic risk engine returned {gate.decision}."
    )
    return DecisionExplanation(
        headline=headline,
        summary=summary,
        final_action=action,
        confidence=consensus.confidence,
        positive_factors=positive,
        negative_factors=negative,
        agent_votes=[
            {
                "agent": decision.display_name,
                "agent_name": decision.agent_name,
                "action": decision.action,
                "confidence": decision.confidence,
                "thesis": decision.thesis,
                "evidence": [item.model_dump() for item in decision.evidence],
                "engine": decision.engine,
            }
            for decision in decisions
        ],
        consensus_explanation=f"Code-weighted votes from {agreeing} produced a score of {consensus.weighted_score:+.3f}; no model controls the aggregation rule.",
        risk_decision=gate.decision,
        triggered_rules=[check.model_dump() for check in gate.checks if not check.passed or check.rule_id in {"R001", "R004"}],
        requested_size=proposal.requested_position_pct if proposal else 0,
        approved_size=gate.approved_position_pct,
        invalidation_conditions=invalidation,
        execution_status=execution.status if execution else None,
    )


def build_hedge_explanation(
    symbol: str,
    decisions: list[AgentDecision],
    consensus: ConsensusDecision,
    plan: HedgePlan,
    gate: RiskGateResult,
    execution: ExecutionOrder | None = None,
) -> DecisionExplanation:
    if plan.action == "OPEN" and plan.contract:
        headline = f"{symbol} protective put — {gate.decision.lower()}d"
        contract_detail = (
            f"{plan.contracts} × {plan.contract.expiration_date.isoformat()} "
            f"${plan.contract.strike_price:g} put"
        )
        summary = (
            f"SentinelAlpha measured {plan.risk.level.lower()} portfolio risk at "
            f"{plan.risk.score:.0%} and proposed {contract_detail}, protecting "
            f"{plan.actual_hedge_ratio:.0%} of the {symbol} position for at most "
            f"${plan.estimated_premium:,.2f}. The deterministic hedge gate returned "
            f"{gate.decision}."
        )
    else:
        headline = f"{symbol} hedge remains inactive"
        summary = (
            f"SentinelAlpha measured portfolio risk at {plan.risk.score:.0%}. "
            f"No protective option order was created because {plan.rationale[0]}"
        )

    return DecisionExplanation(
        headline=headline,
        summary=summary,
        final_action="BUY" if plan.action == "OPEN" else "HOLD",
        confidence=plan.risk.score,
        positive_factors=plan.rationale[:6],
        negative_factors=[
            "Option premium creates portfolio carry cost",
            "Protection can expire without intrinsic value",
            "Wide bid/ask spreads can reduce execution quality",
        ],
        agent_votes=[
            {
                "agent": decision.display_name,
                "agent_name": decision.agent_name,
                "action": decision.action,
                "confidence": decision.confidence,
                "thesis": decision.thesis,
                "evidence": [item.model_dump() for item in decision.evidence],
                "engine": decision.engine,
            }
            for decision in decisions
        ],
        consensus_explanation=(
            f"The council's {consensus.direction} risk posture was converted into a "
            "bounded protective-put proposal by deterministic hedge-selection code; "
            "agents never selected or submitted the broker order directly."
        ),
        risk_decision=gate.decision,
        triggered_rules=[
            check.model_dump()
            for check in gate.checks
            if not check.passed or check.rule_id in {"H003", "H007", "H008", "H016"}
        ],
        requested_size=plan.premium_pct_equity,
        approved_size=gate.approved_position_pct,
        invalidation_conditions=plan.release_conditions,
        execution_status=execution.status if execution else None,
    )
