from dataclasses import replace

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config import get_settings
from app.db import Base
from app.schemas import AnalysisRequest
from app.services.risk import RiskControlState
from app.services.workflow import WorkflowService
from app.services.fixtures import demo_account


def service():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, expire_on_commit=False)()
    settings = get_settings()
    return WorkflowService(session, settings, RiskControlState(settings)), session


def test_risk_modification_scenario_reduces_eight_percent_to_four():
    workflow, session = service()
    try:
        result = workflow.analyze(AnalysisRequest(symbol="AAPL"))
        assert result.consensus.direction == "BUY"
        assert result.risk_gate.decision == "MODIFY"
        assert result.risk_gate.requested_position_pct == 0.08
        assert result.risk_gate.approved_position_pct == 0.04
        assert result.status == "AWAITING_APPROVAL"
        assert result.execution is None
    finally:
        session.close()


def test_information_risk_escalates_without_order():
    workflow, session = service()
    try:
        result = workflow.analyze(
            AnalysisRequest(symbol="NVDA", scenario="information_risk")
        )
        assert result.risk_review.verdict == "REJECT_RECOMMENDATION"
        assert result.risk_gate.decision == "ESCALATE"
        assert result.status == "ESCALATED"
        assert result.execution is None
    finally:
        session.close()


def test_soc_scenario_fails_closed_and_emits_behavior_alerts():
    workflow, session = service()
    try:
        result = workflow.analyze(AnalysisRequest(symbol="TSLA", scenario="agent_soc"))
        assert result.risk_gate.decision == "REJECT"
        assert result.status == "REJECTED"
        assert {alert.rule_id for alert in result.soc_alerts} >= {"SOC002", "SOC004", "SOC005", "SOC008", "SOC009"}
    finally:
        session.close()


def test_explicit_approval_creates_one_simulated_paper_order():
    workflow, session = service()
    try:
        pending = workflow.analyze(AnalysisRequest(symbol="AAPL"))
        completed = workflow.approve(pending.workflow_run_id)
        repeated = workflow.approve(pending.workflow_run_id)

        assert completed.status == "COMPLETED"
        assert completed.execution is not None
        assert completed.execution.execution_mode == "SIMULATED_PAPER"
        assert repeated.execution.provider_order_id == completed.execution.provider_order_id
        assert len(workflow.repository.list_orders()) == 1
    finally:
        session.close()


def test_replay_never_auto_executes():
    workflow, session = service()
    try:
        pending = workflow.analyze(AnalysisRequest(symbol="AAPL"))
        replay = workflow.replay(pending.workflow_run_id)
        assert replay.replay_of == pending.workflow_run_id
        assert replay.execution is None
        assert replay.status == "AWAITING_APPROVAL"
    finally:
        session.close()


def test_portfolio_protection_builds_an_executable_protective_put():
    workflow, session = service()
    try:
        result = workflow.analyze(
            AnalysisRequest(
                symbol="NVDA",
                scenario="portfolio_protection",
                strategy="PROTECTIVE_PUT",
            )
        )

        assert result.strategy == "PROTECTIVE_PUT"
        assert result.consensus.direction == "SELL"
        assert result.hedge_plan is not None
        assert result.hedge_plan.action == "OPEN"
        assert result.hedge_plan.contract is not None
        assert result.hedge_plan.contract.option_type == "PUT"
        assert result.hedge_plan.contracts == 1
        assert result.hedge_plan.actual_hedge_ratio == 1
        assert result.proposal is not None
        assert result.proposal.instrument_type == "OPTION"
        assert result.proposal.position_intent == "BUY_TO_OPEN"
        assert result.risk_gate.decision == "APPROVE"
        assert {check.rule_id for check in result.risk_gate.checks} == {
            f"H{index:03d}" for index in range(1, 18)
        }
        assert result.status == "AWAITING_APPROVAL"
    finally:
        session.close()


def test_protective_put_approval_records_contract_quantity_and_limit():
    workflow, session = service()
    try:
        pending = workflow.analyze(
            AnalysisRequest(
                symbol="NVDA",
                scenario="portfolio_protection",
                strategy="PROTECTIVE_PUT",
            )
        )
        completed = workflow.approve(pending.workflow_run_id)

        assert completed.status == "COMPLETED"
        assert completed.execution is not None
        assert completed.execution.instrument_type == "OPTION"
        assert completed.execution.quantity == 1
        assert completed.execution.limit_price == pending.hedge_plan.limit_price
        assert completed.execution.position_intent == "BUY_TO_OPEN"
        assert completed.execution.execution_interface == "SIMULATED_REPLAY"
    finally:
        session.close()


def test_protective_put_fails_closed_without_options_level_two():
    workflow, session = service()
    try:
        restricted = demo_account("NVDA", "portfolio_protection").model_copy(
            update={"options_approved_level": 1, "options_trading_level": 1}
        )
        workflow.alpaca.account = lambda *_args, **_kwargs: restricted

        result = workflow.analyze(
            AnalysisRequest(
                symbol="NVDA",
                scenario="portfolio_protection",
                strategy="PROTECTIVE_PUT",
            )
        )

        permission = next(
            check for check in result.risk_gate.checks if check.rule_id == "H017"
        )
        assert permission.passed is False
        assert result.risk_gate.decision == "REJECT"
        assert result.status == "REJECTED"
        assert result.execution is None
    finally:
        session.close()


def test_autonomous_protective_put_is_server_gated_and_paper_only():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, expire_on_commit=False)()
    settings = replace(get_settings(), auto_execute_paper=True)
    workflow = WorkflowService(session, settings, RiskControlState(settings))
    try:
        result = workflow.analyze(
            AnalysisRequest(
                symbol="NVDA",
                scenario="portfolio_protection",
                strategy="PROTECTIVE_PUT",
                auto_execute=True,
            )
        )

        assert result.status == "COMPLETED"
        assert result.execution is not None
        assert result.execution.execution_mode == "SIMULATED_PAPER"
        assert result.execution.position_intent == "BUY_TO_OPEN"
        assert result.execution.execution_interface == "SIMULATED_REPLAY"
    finally:
        session.close()


def test_policy_updates_reject_unsafe_ranges():
    settings = get_settings()
    controls = RiskControlState(settings)
    try:
        controls.update("min_consensus_confidence", -0.5)
    except ValueError as error:
        assert "between 0 and 1" in str(error)
    else:
        raise AssertionError("unsafe confidence threshold should be rejected")

    try:
        controls.update("min_agreeing_agents", 2.5)
    except ValueError as error:
        assert "whole number" in str(error)
    else:
        raise AssertionError("fractional agent threshold should be rejected")
