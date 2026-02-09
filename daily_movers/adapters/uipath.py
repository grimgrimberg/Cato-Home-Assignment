from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

from daily_movers.config import load_config
from daily_movers.errors import DailyMoversError
from daily_movers.pipeline.orchestrator import RunRequest, run_daily_movers as run_pipeline


_ALLOWED_MODES = {"movers", "watchlist"}
_ALLOWED_REGIONS = {"us", "il", "uk", "eu", "crypto"}
_ALLOWED_SOURCES = {"auto", "most-active", "universe"}


def _coerce_iso_date(value: Any) -> str:
    if value is None or (isinstance(value, str) and not value.strip()):
        return date.today().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if not isinstance(value, str):
        raise ValueError("date must be a YYYY-MM-DD string")
    try:
        return date.fromisoformat(value.strip()).isoformat()
    except ValueError as exc:
        raise ValueError("date must be a YYYY-MM-DD string") from exc


def _coerce_int(value: Any, *, field: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{field} must be an integer")
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be an integer") from exc
    return parsed


def _coerce_bool(value: Any, *, field: str) -> bool:
    if value is None:
        return False
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        if value in (0, 1):
            return bool(value)
        raise ValueError(f"{field} must be a boolean")
    if isinstance(value, str):
        v = value.strip().lower()
        if v in {"true", "1", "yes", "y", "on"}:
            return True
        if v in {"false", "0", "no", "n", "off", ""}:
            return False
        raise ValueError(f"{field} must be a boolean")
    raise ValueError(f"{field} must be a boolean")


def _coerce_optional_path(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, str):
        v = value.strip()
        return v or None
    raise ValueError("watchlist must be a path string")


def run_daily_movers_adapter(
    out_dir: str,
    *,
    date: Any = None,
    mode: Any = "movers",
    region: Any = "us",
    source: Any = "auto",
    top: Any = 20,
    watchlist: Any = None,
    send_email: Any = False,
) -> dict[str, Any]:
    """UiPath-friendly adapter entrypoint.

    Strictly validates/coerces inputs (UiPath frequently passes strings) and returns
    a JSON-serializable payload with stable keys: {status, summary, paths}.
    """
    try:
        if not isinstance(out_dir, str) or not out_dir.strip():
            raise ValueError("out_dir must be a non-empty string")

        normalized_date = _coerce_iso_date(date)
        normalized_mode = str(mode).strip().lower() if mode is not None else ""
        normalized_region = str(region).strip().lower() if region is not None else ""
        normalized_source = str(source).strip().lower() if source is not None else ""
        normalized_top = _coerce_int(top, field="top")
        normalized_watchlist = _coerce_optional_path(watchlist)
        normalized_send_email = _coerce_bool(send_email, field="send_email")

        if normalized_mode not in _ALLOWED_MODES:
            raise ValueError(f"mode must be one of {sorted(_ALLOWED_MODES)}")
        if normalized_region not in _ALLOWED_REGIONS:
            raise ValueError(f"region must be one of {sorted(_ALLOWED_REGIONS)}")
        if normalized_source not in _ALLOWED_SOURCES:
            raise ValueError(f"source must be one of {sorted(_ALLOWED_SOURCES)}")
        if normalized_top <= 0:
            raise ValueError("top must be a positive integer")

        if normalized_mode == "watchlist":
            if not normalized_watchlist:
                raise ValueError("watchlist is required when mode='watchlist'")
            if not Path(normalized_watchlist).exists():
                raise ValueError(f"watchlist path not found: {normalized_watchlist}")
        else:
            if normalized_watchlist:
                raise ValueError("watchlist must be omitted when mode='movers'")

        cfg = load_config()
        request = RunRequest(
            date=normalized_date,
            mode=normalized_mode,
            region=normalized_region,
            source=normalized_source,
            top=normalized_top,
            watchlist=normalized_watchlist,
            out_dir=out_dir,
            send_email=normalized_send_email,
        )

        artifacts = run_pipeline(request=request, config=cfg)
        payload = artifacts.model_dump()
        return {
            "status": payload["status"],
            "summary": payload["summary"],
            "paths": payload["paths"],
        }
    except TypeError:
        # Reject unknown/incorrect parameters hard (best for UiPath workflow correctness).
        raise
    except DailyMoversError as exc:
        return {
            "status": "failed",
            "summary": {
                "error_type": exc.__class__.__name__,
                "error_message": str(exc),
                "stage": getattr(exc, "stage", None),
                "url": getattr(exc, "url", None),
            },
            "paths": {},
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "status": "failed",
            "summary": {
                "error_type": exc.__class__.__name__,
                "error_message": str(exc),
            },
            "paths": {},
        }


# Required adapter signature for migration compatibility.
def run_daily_movers(
    out_dir: str,
    *,
    date: Any = None,
    mode: Any = "movers",
    region: Any = "us",
    source: Any = "auto",
    top: Any = 20,
    watchlist: Any = None,
    send_email: Any = False,
) -> dict[str, Any]:
    return run_daily_movers_adapter(
        out_dir,
        date=date,
        mode=mode,
        region=region,
        source=source,
        top=top,
        watchlist=watchlist,
        send_email=send_email,
    )
