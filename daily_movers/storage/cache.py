from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any, Protocol

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
        max_retries: int = 2,
    ) -> None:
        self.cache_dir = cache_dir
        self.default_ttl_seconds = default_ttl_seconds
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": user_agent})
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
        cached = self._read_cache(cache_key, ttl)
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

        attempts = self.max_retries + 1
        for attempt in range(1, attempts + 1):
            start = time.perf_counter()
            try:
                response = self.session.get(
                    url,
                    params=params,
                    headers=headers,
                    timeout=self.timeout_seconds,
                )
                latency_ms = int((time.perf_counter() - start) * 1000)
                if response.status_code >= 400:
                    raise HTTPFetchError(
                        f"HTTP {response.status_code} from {response.url}",
                        stage=stage,
                        url=response.url,
                    )
                body = response.text
                self._write_cache(cache_key, body)
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

    def _read_cache(self, key: str, ttl_seconds: int) -> str | None:
        path = self._cache_path(key)
        if not path.exists():
            return None
        try:
            with path.open("r", encoding="utf-8") as f:
                payload = json.load(f)
            created = float(payload.get("created_at_epoch", 0))
            age = time.time() - created
            if age > ttl_seconds:
                return None
            return str(payload["body"])
        except Exception:
            return None

    def _write_cache(self, key: str, body: str) -> None:
        path = self._cache_path(key)
        payload = {
            "created_at_epoch": time.time(),
            "body": body,
        }
        try:
            with path.open("w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=True)
        except Exception:
            # Cache write failure is intentionally non-fatal.
            return
