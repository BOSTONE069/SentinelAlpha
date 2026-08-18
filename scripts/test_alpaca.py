"""Validate SentinelAlpha's locked Alpaca paper-trading connection."""

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "apps" / "api"))

from app.config import get_settings  # noqa: E402
from app.services.alpaca import AlpacaService  # noqa: E402


def main() -> int:
    settings = get_settings()
    print(f"Endpoint: {settings.alpaca_trading_api_url}")
    print("Mode: paper (locked)")
    if not settings.alpaca_configured:
        print("Credentials: not configured")
        print("Add ALPACA_API_KEY and ALPACA_SECRET_KEY to .env, then retry.")
        return 2

    try:
        result = AlpacaService(settings).connection_status()
    except Exception as exc:
        print(f"Connection: failed ({type(exc).__name__})")
        print("Confirm the credentials were generated for the selected paper account.")
        return 1

    safe_result = {
        key: value
        for key, value in result.items()
        if key not in {"api_key", "secret_key"}
    }
    print(json.dumps(safe_result, indent=2))
    if not result.get("alpaca_cli_available"):
        print("Options execution: unavailable (install Alpaca CLI or set ALPACA_CLI_PATH)")
        return 1
    print("Options execution: Alpaca CLI available in paper mode")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
