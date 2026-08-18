# Minimum API

Interactive OpenAPI documentation is served at `/docs`.

All endpoints below except `/health` and `/config/public` require:

```http
Authorization: Bearer <API_AUTH_TOKEN>
```

The token resolves to a user, portfolio, and role. Runs, orders, audit exports,
event streams, and SOC objects are filtered by that portfolio. Viewers receive
`403` for mutations; inaccessible object identifiers return `404`.

Core endpoints:

```text
GET  /api/v1/health
GET  /api/v1/config/public
GET  /api/v1/alpaca/account
GET  /api/v1/alpaca/connection
GET  /api/v1/alpaca/positions
GET  /api/v1/alpaca/clock
GET  /api/v1/alpaca/options/{symbol}/contracts
GET  /api/v1/market/{symbol}/snapshot
GET  /api/v1/market/{symbol}/bars
GET  /api/v1/market/{symbol}/indicators
GET  /api/v1/market/{symbol}/news
POST /api/v1/analysis
GET  /api/v1/audit/export
GET  /api/v1/runs
GET  /api/v1/runs/{run_id}
POST /api/v1/runs/{run_id}/approve
POST /api/v1/runs/{run_id}/reject
POST /api/v1/runs/{run_id}/replay
GET  /api/v1/events/runs/{run_id}
GET  /api/v1/risk/policies
PUT  /api/v1/risk/policies/{key}
POST /api/v1/risk/kill-switch
GET  /api/v1/soc/overview
GET  /api/v1/soc/alerts
GET  /api/v1/orders
```

`GET /api/v1/health` also reports the active coordination backend and whether
Redis is mandatory. A `409` with `Retry-After: 2` means another worker owns the
conflicting workflow lock; `503` indicates a required coordination or provider
dependency is unavailable.

`GET /api/v1/audit/export` downloads all persisted workflows as a versioned JSON
audit bundle. Pass `run_id` to export a single workflow.

Example:

```bash
curl -s http://localhost:8000/api/v1/analysis \
  -H "Authorization: Bearer $API_AUTH_TOKEN" \
  -H 'content-type: application/json' \
  -d '{"symbol":"AAPL","mode":"REPLAY","scenario":"risk_modification","agent_provider":"RULES"}'
```

Protective-put analysis:

```bash
curl -s http://localhost:8000/api/v1/analysis \
  -H "Authorization: Bearer $API_AUTH_TOKEN" \
  -H 'content-type: application/json' \
  -d '{"symbol":"NVDA","mode":"REPLAY","scenario":"portfolio_protection","strategy":"PROTECTIVE_PUT","agent_provider":"RULES"}'
```
