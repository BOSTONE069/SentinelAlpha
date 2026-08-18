"""Seed all three replay scenarios into the local audit database."""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "apps" / "api"))

from app.config import get_settings
from app.db import SessionLocal, init_db
from app.schemas import AnalysisRequest
from app.services.risk import RiskControlState
from app.services.workflow import WorkflowService


def main() -> None:
    init_db()
    settings = get_settings()
    controls = RiskControlState(settings)
    with SessionLocal() as session:
        service = WorkflowService(session, settings, controls)
        for symbol, scenario in [
            ("AAPL", "risk_modification"),
            ("NVDA", "information_risk"),
            ("TSLA", "agent_soc"),
        ]:
            result = service.analyze(AnalysisRequest(symbol=symbol, scenario=scenario))
            print(f"{symbol:<5} {result.risk_gate.decision:<9} {result.workflow_run_id}")


if __name__ == "__main__":
    main()
