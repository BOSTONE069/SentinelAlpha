# Three-minute Track 03 demo

1. Open Hedge Agent. Point out paper mode and the Alpaca CLI execution boundary.
2. Run the NVDA portfolio-protection replay.
3. Show the four defensive opinions and the component-based portfolio risk score.
4. Show the selected 21–45 DTE protective put, approximately 5% OTM strike, integer contract sizing, hedge ratio, bid/ask spread, and maximum premium.
5. Walk through H001–H017: paper mode, underlying ownership, activation score, put type, DTE, strike, size, premium, liquidity, quote freshness, duplicates, daily limit, market hours, semantic review, kill switch, Alpaca CLI interface, and options account level.
6. Show the supervised/autonomous selector. Supervised mode pauses for approval; autonomous mode requires the server-side `AUTO_EXECUTE_PAPER=true` feature gate. Both paths run H001–H017 and remain paper-only.
7. Approve in supervised mode. Replay creates a simulated option order; LIVE sends an idempotent `BUY_TO_OPEN` limit order through Alpaca CLI to paper trading.
8. Open Full explanation. Show the audit-linked contract and the pre-committed release and rebalance conditions.
9. Close with: “SentinelAlpha does not merely reject risk. It detects when protection is justified, buys only bounded protection, and explains when that protection should be removed.”
