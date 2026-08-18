from __future__ import annotations

from ..schemas import AgentDecision, ConsensusDecision

AGENT_WEIGHTS = {"market": 0.25, "news": 0.20, "quant": 0.35, "portfolio": 0.20}
ACTION_SCORE = {"BUY": 1, "HOLD": 0, "SELL": -1}


def build_consensus(decisions: list[AgentDecision]) -> ConsensusDecision:
    if not decisions:
        raise ValueError("at least one agent decision is required")
    weighted_score = sum(
        ACTION_SCORE[decision.action] * decision.confidence * AGENT_WEIGHTS[decision.agent_name]
        for decision in decisions
    )
    if weighted_score >= 0.35:
        direction = "BUY"
    elif weighted_score <= -0.35:
        direction = "SELL"
    else:
        direction = "HOLD"

    supporting = [decision for decision in decisions if decision.action == direction]
    dissenting = [decision for decision in decisions if decision.action != direction]
    supporting_weight = sum(AGENT_WEIGHTS[decision.agent_name] for decision in supporting)
    confidence = (
        sum(decision.confidence * AGENT_WEIGHTS[decision.agent_name] for decision in supporting)
        / supporting_weight
        if supporting_weight
        else max(0.0, 1 - abs(weighted_score))
    )
    agreement = len(supporting) / len(decisions)
    return ConsensusDecision(
        direction=direction,
        confidence=round(confidence, 4),
        weighted_score=round(weighted_score, 4),
        agreement_ratio=round(agreement, 4),
        disagreement_score=round(1 - agreement, 4),
        agreeing_agents=len(supporting),
        total_agents=len(decisions),
        supporting_agents=[decision.agent_name for decision in supporting],
        dissenting_agents=[decision.agent_name for decision in dissenting],
    )
