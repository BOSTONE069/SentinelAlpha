from __future__ import annotations

from dataclasses import dataclass
from hmac import compare_digest

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .config import Settings, get_settings
from .db import Repository


bearer_scheme = HTTPBearer(
    auto_error=False,
    scheme_name="SentinelAlpha bearer token",
    description="Operator token configured with API_AUTH_TOKEN.",
)


@dataclass(frozen=True)
class AuthzContext:
    user_id: str
    portfolio_ids: frozenset[str]
    role: str

    @property
    def can_write(self) -> bool:
        return self.role in {"operator", "admin"}

    @property
    def portfolio_scope(self) -> frozenset[str] | None:
        return None if self.role == "admin" else self.portfolio_ids


def _unauthorized(detail: str = "authentication required") -> HTTPException:
    return HTTPException(
        status_code=401,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


def validate_auth_configuration(settings: Settings) -> None:
    if settings.api_auth_role not in {"viewer", "operator", "admin"}:
        raise RuntimeError("API_AUTH_ROLE must be viewer, operator, or admin")
    if not settings.api_auth_user_id or not settings.api_auth_portfolio_id:
        raise RuntimeError("API auth user and portfolio identifiers are required")
    if settings.app_env.lower() in {"production", "staging"} and (
        not settings.api_auth_token or len(settings.api_auth_token) < 32
    ):
        raise RuntimeError(
            "API_AUTH_TOKEN must be configured with at least 32 characters "
            "outside development"
        )


def require_authenticated_actor(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    settings: Settings = Depends(get_settings),
) -> AuthzContext:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise _unauthorized()
    if not settings.api_auth_token:
        raise HTTPException(503, "API authentication is not configured")
    if not compare_digest(credentials.credentials, settings.api_auth_token):
        raise _unauthorized("invalid bearer token")
    try:
        validate_auth_configuration(settings)
    except RuntimeError as exc:
        raise HTTPException(503, str(exc)) from exc
    return AuthzContext(
        user_id=settings.api_auth_user_id,
        portfolio_ids=frozenset({settings.api_auth_portfolio_id}),
        role=settings.api_auth_role,
    )


def require_write_access(actor: AuthzContext) -> None:
    if not actor.can_write:
        raise HTTPException(403, "operator role required")


def _portfolio_allowed(actor: AuthzContext, portfolio_id: str | None) -> bool:
    return actor.role == "admin" or (
        portfolio_id is not None and portfolio_id in actor.portfolio_ids
    )


def require_run_access(
    repository: Repository,
    actor: AuthzContext,
    run_id: str,
    *,
    write: bool = False,
) -> dict:
    if write:
        require_write_access(actor)
    if not _portfolio_allowed(actor, repository.workflow_portfolio_id(run_id)):
        raise HTTPException(404, "workflow not found")
    payload = repository.get_workflow(run_id)
    if payload is None:
        raise HTTPException(404, "workflow not found")
    return payload


def list_runs_for_actor(
    repository: Repository, actor: AuthzContext, limit: int
) -> list[dict]:
    return repository.list_workflows(limit, portfolio_ids=actor.portfolio_scope)


def require_order_access(
    repository: Repository,
    actor: AuthzContext,
    order_id: str,
    *,
    write: bool = False,
) -> dict:
    if write:
        require_write_access(actor)
    if not _portfolio_allowed(actor, repository.order_portfolio_id(order_id)):
        raise HTTPException(404, "order not found")
    order = repository.get_order(order_id)
    if order is None:
        raise HTTPException(404, "order not found")
    return order


def list_orders_for_actor(
    repository: Repository, actor: AuthzContext, limit: int
) -> list[dict]:
    return repository.list_orders(limit, portfolio_ids=actor.portfolio_scope)


def require_alert_access(
    repository: Repository,
    actor: AuthzContext,
    alert_id: str,
    *,
    write: bool = False,
) -> dict:
    if write:
        require_write_access(actor)
    if not _portfolio_allowed(actor, repository.alert_portfolio_id(alert_id)):
        raise HTTPException(404, "alert not found")
    alert = repository.get_alert(alert_id)
    if alert is None:
        raise HTTPException(404, "alert not found")
    return alert


def list_alerts_for_actor(
    repository: Repository, actor: AuthzContext, limit: int
) -> list[dict]:
    return repository.list_alerts(limit, portfolio_ids=actor.portfolio_scope)
