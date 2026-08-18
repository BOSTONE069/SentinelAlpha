from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api.router import api_router, public_api_router
from .authz import validate_auth_configuration
from .config import get_settings
from .coordination import get_coordination
from .db import Repository, SessionLocal, init_db


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings = get_settings()
    validate_auth_configuration(settings)
    init_db()
    get_coordination().ping()
    from .services.risk import RiskControlState

    with SessionLocal() as db:
        defaults = RiskControlState(get_settings()).policies()
        Repository(db).seed_risk_policies(
            [policy.model_dump(mode="json") for policy in defaults]
        )
    yield


settings = get_settings()
app = FastAPI(
    title="SentinelAlpha API",
    description="Explainable, deterministic supervision for autonomous paper-trading agents.",
    version="0.1.0",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.web_origin],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition"],
)
app.include_router(public_api_router, prefix="/api/v1")
app.include_router(api_router, prefix="/api/v1")


@app.get("/")
def root() -> dict[str, str]:
    return {"name": "SentinelAlpha", "docs": "/docs", "health": "/api/v1/health"}
