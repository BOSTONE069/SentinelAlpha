from datetime import datetime, timezone

from app.schemas import AgentDecision
from app.services.consensus import build_consensus


def decision(agent: str, action: str, confidence: float) -> AgentDecision:
    return AgentDecision(
        agent_name=agent,
        display_name=agent,
        symbol="AAPL",
        action=action,
        confidence=confidence,
        thesis="test",
        evidence=[],
        bullish_factors=[],
        bearish_factors=[],
        risk_flags=[],
        suggested_position_pct=0,
        invalidation_conditions=[],
        data_timestamp=datetime.now(timezone.utc),
    )


def test_consensus_is_code_weighted_and_preserves_dissent():
    result = build_consensus(
        [
            decision("market", "BUY", 0.84),
            decision("news", "BUY", 0.76),
            decision("quant", "BUY", 0.81),
            decision("portfolio", "HOLD", 0.62),
        ]
    )

    assert result.direction == "BUY"
    assert result.agreeing_agents == 3
    assert result.dissenting_agents == ["portfolio"]
    assert result.weighted_score > 0.35


def test_conflicting_low_weight_signals_resolve_to_hold():
    result = build_consensus(
        [
            decision("market", "BUY", 0.40),
            decision("news", "SELL", 0.40),
            decision("quant", "HOLD", 0.80),
            decision("portfolio", "HOLD", 0.80),
        ]
    )
    assert result.direction == "HOLD"
