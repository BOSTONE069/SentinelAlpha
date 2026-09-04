# Deploy SentinelAlpha on Render

The repository's root `render.yaml` creates the complete demo stack:

- `sentinelalpha-web`: Next.js dashboard
- `sentinelalpha-api`: FastAPI API and Alpaca CLI
- `sentinelalpha-postgres`: PostgreSQL persistence
- `sentinelalpha-redis`: Redis-compatible cache and distributed locks

## Before deployment

1. Push this repository to GitHub or GitLab.
2. Create a Render account and connect the Git provider.
3. Confirm that the Alpaca credentials are for **paper trading**, not a live
   brokerage account.

## Create the Blueprint

1. In the Render Dashboard, select **New > Blueprint**.
2. Connect this repository and keep the Blueprint path as `render.yaml`.
3. Provide `ALPACA_API_KEY` and `ALPACA_SECRET_KEY` when prompted if the live
   Alpaca paper-data demo is required. Replay mode works without them.
4. `OPENAI_API_KEY` is optional. Leave it unset when using the bounded RULES
   agents.
5. Apply the Blueprint and wait for both web services to report **Live**.

The Blueprint obtains the public URLs assigned by Render automatically. The
dashboard receives the API URL at build time, and the API receives the dashboard
URL as its only allowed browser origin. PostgreSQL and Key Value use private
Render connection strings and are not exposed publicly.

## Sign in to the dashboard

Production API routes require the randomly generated operator token:

1. Open the `sentinelalpha-api` service in Render.
2. Open **Environment** and reveal/copy `API_AUTH_TOKEN`.
3. Open the `sentinelalpha-web` URL.
4. Go to **Settings > Dashboard authentication**, paste the token, and connect.

Do not add this token to a `NEXT_PUBLIC_*` variable. The dashboard keeps it in
browser session storage.

## Verify the deployment

Open these URLs after Render finishes deploying:

```text
https://<api-host>.onrender.com/api/v1/health
https://<api-host>.onrender.com/docs
https://<web-host>.onrender.com
```

The health response should report `status: "healthy"`,
`coordination_backend: "redis"`, and `redis_required: true`.

If the frontend was built before the API URL was available, select **Manual
Deploy > Clear build cache & deploy** on `sentinelalpha-web`.

## Troubleshoot a missing Dockerfile

Use **New > Blueprint**, not **New > Web Service**, to create the stack. If an
existing manually created service reports `open Dockerfile: no such file or
directory`, update **Settings > Build & Deploy** with these values:

| Service | Root Directory | Dockerfile Path | Docker Build Context |
| --- | --- | --- | --- |
| `sentinelalpha-api` | *(blank)* | `./apps/api/Dockerfile` | `./apps/api` |
| `sentinelalpha-web` | *(blank)* | `./apps/web/Dockerfile` | `./apps/web` |

Save the settings and select **Manual Deploy > Clear build cache & deploy**. A
service created manually does not automatically import the settings from
`render.yaml`. You can instead delete only that failed service and recreate the
complete stack through **New > Blueprint**.

## Free-tier boundaries

- Free web services sleep after inactivity, so the first request can be slow.
- Free Key Value data can disappear on a restart. This is safe for this cache
  and lock use, but active locks do not survive a restart.
- Free PostgreSQL expires 30 days after creation and has no backups. Export the
  audit trail before it expires or upgrade the database.
- Keep `LIVE_TRADING_ENABLED=false`. SentinelAlpha is configured for Alpaca
  paper trading only.
