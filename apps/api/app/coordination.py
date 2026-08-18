from __future__ import annotations

import json
import threading
from contextlib import contextmanager
from functools import lru_cache
from typing import Iterator

from .config import Settings, get_settings


class CoordinationUnavailable(RuntimeError):
    """Raised when a required Redis coordination backend is unavailable."""


class ConcurrentWorkflowError(RuntimeError):
    """Raised when another worker already owns a workflow lock."""


class CoordinationBackend:
    """Redis cache/locks with an explicit single-process development fallback.

    Production deployments should set ``REDIS_REQUIRED=true``. In development,
    an absent Redis URL uses the in-memory implementation so SQLite/replay mode
    remains zero-configuration.
    """

    def __init__(self, settings: Settings):
        self.settings = settings
        self._key_prefix = f"sentinelalpha:{settings.app_env}"
        self._client = None
        self._client_lock = threading.Lock()
        self._local_locks: dict[str, threading.Lock] = {}
        self._local_locks_guard = threading.Lock()
        self._local_cache: dict[str, tuple[float, str]] = {}
        self._local_cache_guard = threading.Lock()

    @property
    def backend_name(self) -> str:
        return "redis" if self.settings.redis_url else "memory"

    def _redis(self):
        if not self.settings.redis_url:
            return None
        with self._client_lock:
            if self._client is None:
                try:
                    from redis import Redis
                except ImportError as exc:
                    raise CoordinationUnavailable(
                        "Install the redis dependency to use REDIS_URL"
                    ) from exc
                self._client = Redis.from_url(
                    self.settings.redis_url,
                    decode_responses=True,
                    socket_connect_timeout=1.0,
                    socket_timeout=1.0,
                    health_check_interval=30,
                )
        return self._client

    def _redis_failure(self, operation: str, exc: Exception) -> None:
        if self.settings.redis_required:
            raise CoordinationUnavailable(
                f"Redis is required but {operation} failed: {type(exc).__name__}"
            ) from exc

    def get_json(self, key: str) -> dict | None:
        client = self._redis()
        if client is not None:
            try:
                raw = client.get(f"{self._key_prefix}:cache:{key}")
                return json.loads(raw) if raw else None
            except Exception as exc:
                self._redis_failure("cache read", exc)
                return None

        import time

        now = time.monotonic()
        with self._local_cache_guard:
            item = self._local_cache.get(key)
            if item is None:
                return None
            expires_at, raw = item
            if expires_at <= now:
                self._local_cache.pop(key, None)
                return None
        return json.loads(raw)

    def set_json(self, key: str, value: dict, ttl_seconds: int | None = None) -> None:
        ttl = ttl_seconds or self.settings.cache_ttl_seconds
        raw = json.dumps(value, separators=(",", ":"), default=str)
        client = self._redis()
        if client is not None:
            try:
                client.setex(f"{self._key_prefix}:cache:{key}", ttl, raw)
            except Exception as exc:
                self._redis_failure("cache write", exc)
            return

        import time

        with self._local_cache_guard:
            self._local_cache[key] = (time.monotonic() + ttl, raw)

    def delete(self, key: str) -> None:
        client = self._redis()
        if client is not None:
            try:
                client.delete(f"{self._key_prefix}:cache:{key}")
            except Exception as exc:
                self._redis_failure("cache invalidation", exc)
            return
        with self._local_cache_guard:
            self._local_cache.pop(key, None)

    def ping(self) -> bool:
        client = self._redis()
        if client is None:
            return True
        try:
            return bool(client.ping())
        except Exception as exc:
            self._redis_failure("health check", exc)
            return False

    def _local_lock(self, name: str) -> threading.Lock:
        with self._local_locks_guard:
            return self._local_locks.setdefault(name, threading.Lock())

    @contextmanager
    def lock(
        self,
        name: str,
        *,
        wait_seconds: float | None = None,
        ttl_seconds: int | None = None,
    ) -> Iterator[None]:
        wait = self.settings.workflow_lock_wait_seconds if wait_seconds is None else wait_seconds
        ttl = self.settings.workflow_lock_ttl_seconds if ttl_seconds is None else ttl_seconds
        client = self._redis()

        if client is not None:
            redis_lock = client.lock(
                f"{self._key_prefix}:lock:{name}",
                timeout=ttl,
                blocking_timeout=wait if wait > 0 else None,
                # The renewal thread must share the ownership token.
                thread_local=False,
            )
            try:
                acquired = redis_lock.acquire(blocking=wait > 0)
            except Exception as exc:
                self._redis_failure("lock acquisition", exc)
            else:
                if not acquired:
                    raise ConcurrentWorkflowError(
                        f"A conflicting workflow is already running ({name})"
                    )
                stop_renewal = threading.Event()
                renewal_failures: list[Exception] = []

                def renew() -> None:
                    interval = max(1.0, ttl / 3)
                    while not stop_renewal.wait(interval):
                        try:
                            redis_lock.extend(ttl, replace_ttl=True)
                        except Exception as exc:
                            renewal_failures.append(exc)
                            return

                renewal_thread = threading.Thread(
                    target=renew,
                    name=f"sentinelalpha-lock-{name}",
                    daemon=True,
                )
                renewal_thread.start()
                operation_failed = False
                try:
                    yield
                except BaseException:
                    operation_failed = True
                    raise
                finally:
                    stop_renewal.set()
                    renewal_thread.join(timeout=1.0)
                    try:
                        if redis_lock.owned():
                            redis_lock.release()
                    except Exception as exc:
                        self._redis_failure("lock release", exc)
                    if renewal_failures and not operation_failed:
                        self._redis_failure("lock renewal", renewal_failures[0])
                return

        local_lock = self._local_lock(name)
        acquired = (
            local_lock.acquire(timeout=wait)
            if wait > 0
            else local_lock.acquire(blocking=False)
        )
        if not acquired:
            raise ConcurrentWorkflowError(
                f"A conflicting workflow is already running ({name})"
            )
        try:
            yield
        finally:
            local_lock.release()


@lru_cache
def get_coordination() -> CoordinationBackend:
    return CoordinationBackend(get_settings())
