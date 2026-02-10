from __future__ import annotations

"""Best-effort HTTP client with caching, retries, and polite concurrency.

Why this exists:
- Yahoo endpoints can be flaky / rate-limited.
- Many pipeline stages request overlapping URLs.

Design:
- On cache hit: return immediately (no network).
- On miss: GET with retry/backoff.
- Concurrency: a per-host semaphore limits parallel requests to the same domain.
- Cache writes are non-fatal: a run should still succeed if caching fails.

Cache format:
- One JSON file per request key under CACHE_DIR.
- Body is stored as text (JSON responses are decoded by get_json).
"""

import hashlib
import json
import random
import threading
import time
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import urlparse

import requests

from daily_movers.errors import HTTPFetchError
from daily_movers.storage.runs import StructuredLogger


class HttpClient(Protocol):
    def get_json(
        self,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        stage: str,
        logger: StructuredLogger,
    ) -> dict[str, Any]: ...

    def get_text(
        self,
        url: str,
        *,
        stage: str,
        logger: StructuredLogger,
    ) -> str: ...


class CachedHttpClient:
    def __init__(
        self,
        *,
        cache_dir: Path,
        default_ttl_seconds: int,
        timeout_seconds: int,
        user_agent: str,
        max_requests_per_host: int = 5,
        max_retries: int = 2,
    ) -> None:
        self.cache_dir = cache_dir
        self.default_ttl_seconds = default_ttl_seconds
        self.timeout_seconds = timeout_seconds
        self.user_agent = user_agent
        self.max_requests_per_host = max_requests_per_host
        self.max_retries = max_retries
        self._session_local = threading.local()
        self._host_semaphores: dict[str, threading.BoundedSemaphore] = {}
        self._host_lock = threading.Lock()
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def get_json(
        self,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        ttl_seconds: int | None = None,
        stage: str,
        logger: StructuredLogger,
    ) -> dict[str, Any]:
        text = self.get_text(
            url,
            params=params,
            headers=headers,
            ttl_seconds=ttl_seconds,
            stage=stage,
            logger=logger,
        )
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise HTTPFetchError(
                f"JSON parse failed for {url}: {exc}",
                stage=stage,
                url=url,
            ) from exc

    def get_text(
        self,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        ttl_seconds: int | None = None,
        stage: str,
        logger: StructuredLogger,
    ) -> str:
        ttl = ttl_seconds if ttl_seconds is not None else self.default_ttl_seconds
        cache_key = self._cache_key("GET", url, params)

        # Read-through cache: avoid re-downloading the same pages during a run.
        cached, cache_age = self._read_cache(cache_key, ttl)
        if cached is not None:
            logger.info(
                "http_cache_hit",
                stage=stage,
                url=url,
                status="ok",
                retries=0,
                fallback_used=False,
            )
            return cached
        if cache_age is not None:
            logger.info(
                "http_cache_expired",
                stage=stage,
                url=url,
                status="ok",
                retries=0,
                fallback_used=False,
                age_seconds=int(cache_age),
                ttl_seconds=ttl,
            )

        # Retry loop: handles transient network issues and common retryable HTTP
        # status codes (408/429/5xx).
        attempts = self.max_retries + 1
        for attempt in range(1, attempts + 1):
            start = time.perf_counter()
            try:
                session = self._get_session()
                # Limit concurrent requests per host to reduce throttling.
                semaphore = self._get_semaphore(url)
                with semaphore:
                    response = session.get(
                        url,
                        params=params,
                        headers=headers,
                        timeout=self.timeout_seconds,
                    )
                latency_ms = int((time.perf_counter() - start) * 1000)
                status_code = response.status_code
                if status_code >= 400:
                    retryable = status_code in {408, 429, 500, 502, 503, 504}
                    if retryable and attempt < attempts:
                        logger.warning(
                            "http_fetch_retry",
                            stage=stage,
                            url=response.url,
                            error_type="HTTPStatusError",
                            error_message=f"HTTP {status_code} from {response.url}",
                            retries=attempt - 1,
                        )
                        self._sleep_backoff(
                            attempt=attempt,
                            response=response,
                        )
                        continue
                    raise HTTPFetchError(
                        f"HTTP {status_code} from {response.url}",
                        stage=stage,
                        url=response.url,
                    )
                body = response.text
                self._write_cache(
                    cache_key,
                    body,
                    status_code=status_code,
                    content_type=response.headers.get("Content-Type"),
                    ttl_seconds=ttl,
                )
                logger.info(
                    "http_fetch",
                    stage=stage,
                    url=response.url,
                    latency_ms=latency_ms,
                    retries=attempt - 1,
                    fallback_used=False,
                )
                return body
            except (requests.RequestException, HTTPFetchError) as exc:
                is_last = attempt == attempts
                logger.warning(
                    "http_fetch_retry" if not is_last else "http_fetch_failed",
                    stage=stage,
                    url=url,
                    error_type=exc.__class__.__name__,
                    error_message=str(exc),
                    retries=attempt - 1,
                )
                if is_last:
                    if isinstance(exc, HTTPFetchError):
                        raise exc
                    raise HTTPFetchError(str(exc), stage=stage, url=url) from exc
                self._sleep_backoff(attempt=attempt, response=None)
        raise HTTPFetchError("unexpected retry loop termination", stage=stage, url=url)

    def _cache_key(
        self,
        method: str,
        url: str,
        params: dict[str, Any] | None,
    ) -> str:
        payload = {
            "method": method,
            "url": url,
            "params": params or {},
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def _cache_path(self, key: str) -> Path:
        return self.cache_dir / f"{key}.json"

    def _read_cache(self, key: str, ttl_seconds: int) -> tuple[str | None, float | None]:
        path = self._cache_path(key)
        if not path.exists():
            return None, None
        try:
            with path.open("r", encoding="utf-8") as f:
                payload = json.load(f)
            created = float(payload.get("created_at_epoch", 0))
            age = time.time() - created
            if age > ttl_seconds:
                return None, age
            return str(payload["body"]), None
        except Exception:
            return None, None

    def _write_cache(
        self,
        key: str,
        body: str,
        *,
        status_code: int,
        content_type: str | None,
        ttl_seconds: int,
    ) -> None:
        path = self._cache_path(key)
        tmp_path = path.with_suffix(".tmp")
        payload = {
            "created_at_epoch": time.time(),
            "body": body,
            "status_code": status_code,
            "content_type": content_type,
            "ttl_seconds": ttl_seconds,
        }
        try:
            with tmp_path.open("w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=True)
            tmp_path.replace(path)
        except Exception:
            # Cache write failure is intentionally non-fatal.
            return

    def _get_session(self) -> requests.Session:
        session = getattr(self._session_local, "session", None)
        if session is None:
            session = requests.Session()
            session.headers.update({"User-Agent": self.user_agent})
            self._session_local.session = session
        return session

    def _get_semaphore(self, url: str) -> threading.BoundedSemaphore:
        host = urlparse(url).netloc or "default"
        with self._host_lock:
            semaphore = self._host_semaphores.get(host)
            if semaphore is None:
                semaphore = threading.BoundedSemaphore(self.max_requests_per_host)
                self._host_semaphores[host] = semaphore
            return semaphore

    def _sleep_backoff(self, *, attempt: int, response: requests.Response | None) -> None:
        delay = min(6.0, 0.5 * (2 ** (attempt - 1)) + random.uniform(0, 0.5))
        retry_after = _parse_retry_after(response)
        if retry_after is not None:
            delay = max(delay, retry_after)
        time.sleep(delay)


def _parse_retry_after(response: requests.Response | None) -> float | None:
    if response is None:
        return None
    value = response.headers.get("Retry-After")
    if not value:
        return None
    value = value.strip()
    try:
        return float(value)
    except ValueError:
        return None
