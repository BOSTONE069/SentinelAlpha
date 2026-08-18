# Architecture

SentinelAlpha separates ambiguous interpretation from capital-control policy.

```text
Next.js dashboard
      ↓ HTTP / SSE
FastAPI workflow service
      ├── market/news/portfolio context
      ├── four bounded analytical agents
      ├── code-derived consensus
      ├── independent semantic risk review
      ├── deterministic equity risk engine (R001–R014)
      ├── Hedge Agent → option chain, strike/expiry, hedge ratio
      ├── deterministic option risk engine (H001–H017)
      ├── explicit human approval
      ├── execution service → Alpaca SDK (equities) / CLI (options), paper only
      └── explanation + SOC + audit persistence

PostgreSQL authoritative state
      ├── normalized workflow/decision/risk/order tables
      ├── row locks for approval/rejection transitions
      └── optimistic version counters on mutable rows

Redis ephemeral coordination
      ├── cached workflow read models
      ├── short-lived market/news/account provider reads
      └── distributed analysis/approval/policy locks
```

## Trust boundaries

1. Operational routes require a bearer token that resolves to an actor role and portfolio scope; object authorization happens before cached data is returned.
2. News is untrusted data and is placed in an explicit `UNTRUSTED_NEWS_CONTENT` field for model-backed analysis.
3. Agents return Pydantic-validated opinions and have no broker client.
4. Consensus is code with fixed weights: market 25%, news 20%, quant 35%, portfolio 20%.
5. The risk engine re-evaluates every rule at approval time, preventing old decisions from bypassing policy changes, stale-data limits, duplicates, or the kill switch.
6. Only `AlpacaService.submit` can create an order. Replay uses a different, clearly labeled simulation branch.
7. Protective puts use integer contract sizing, fresh quotes, limit prices, explicit `BUY_TO_OPEN` intent, and the Alpaca CLI without a live-trading flag.
8. Workflow, hedge-plan, order, and alert records are linked by workflow ID.
9. Redis is never authoritative: losing cached values does not lose workflows,
   orders, policies, alerts, or audit history.
10. Multi-worker production starts only with Redis available when
   `REDIS_REQUIRED=true`; local SQLite mode uses a process-local fallback.

## Modes

- `REPLAY`: deterministic fixtures, current timestamps, no network dependency, no real broker submission.
- `LIVE`: Alpaca paper account/data and optional OpenAI agents. Missing configuration fails closed.
