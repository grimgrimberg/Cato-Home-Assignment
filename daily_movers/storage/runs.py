from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from threading import Lock
from typing import Any

from daily_movers.models import utc_now_iso


@dataclass
class StructuredLogger:
    path: Path
    run_id: str

    def __post_init__(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = Lock()

    def log(
        self,
        *,
        level: str,
        event: str,
        stage: str,
        symbol: str | None = None,
        status: str = "ok",
        error_type: str | None = None,
        error_message: str | None = None,
        url: str | None = None,
        latency_ms: int | None = None,
        retries: int = 0,
        fallback_used: bool = False,
        **extra: Any,
    ) -> None:
        payload: dict[str, Any] = {
            "timestamp": utc_now_iso(),
            "level": level.lower(),
            "event": event,
            "run_id": self.run_id,
            "stage": stage,
            "symbol": symbol,
            "status": status,
            "error_type": error_type,
            "error_message": error_message,
            "url": url,
            "latency_ms": latency_ms,
            "retries": retries,
            "fallback_used": fallback_used,
        }
        payload.update(extra)
        with self._lock:
            with self.path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(payload, ensure_ascii=True) + "\n")

    def info(self, event: str, stage: str, **kwargs: Any) -> None:
        self.log(level="info", event=event, stage=stage, **kwargs)

    def warning(self, event: str, stage: str, **kwargs: Any) -> None:
        self.log(level="warning", event=event, stage=stage, **kwargs)

    def error(self, event: str, stage: str, **kwargs: Any) -> None:
        self.log(level="error", event=event, stage=stage, status="error", **kwargs)


def ensure_run_dir(out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    return out_dir


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=True)


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=True) + "\n")
