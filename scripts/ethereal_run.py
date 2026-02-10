from __future__ import annotations

import csv
import sys
import webbrowser
from datetime import datetime, timezone
from pathlib import Path

# Ensure imports work when this file is executed directly (sys.path[0] becomes
# the scripts/ directory, not the repo root).
WORKSPACE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WORKSPACE_ROOT))

from daily_movers.config import load_config
from daily_movers.pipeline.orchestrator import RunRequest, run_daily_movers


def _utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")


def _read_ethereal_smtp_row(path: Path) -> dict[str, str]:
    if not path.exists():
        raise FileNotFoundError(f"credentials file not found: {path}")

    with path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if not row:
                continue
            if (row.get("Service") or "").strip().upper() == "SMTP":
                return {k: (v or "").strip() for k, v in row.items() if k}

    raise ValueError("No SMTP row found in credentials.csv")


def main() -> int:
    # Prefer SMTP config from .env (or environment variables). Only fall back
    # to credentials.csv if SMTP isn't configured.
    cfg = load_config(env_file=str(WORKSPACE_ROOT / ".env"))

    if not cfg.smtp_ready:
        creds_path = WORKSPACE_ROOT / "credentials.csv"
        smtp_row = _read_ethereal_smtp_row(creds_path)

        host = smtp_row.get("Hostname")
        port_text = smtp_row.get("Port")
        username = smtp_row.get("Username")
        password = smtp_row.get("Password")

        if not host or not port_text or not username or not password:
            raise ValueError("credentials.csv SMTP row is missing Hostname/Port/Username/Password")

        try:
            port = int(port_text)
        except ValueError as exc:
            raise ValueError(f"Invalid SMTP port in credentials.csv: {port_text}") from exc

        cfg = cfg.model_copy(
            update={
                "smtp_host": host,
                "smtp_port": port,
                "smtp_username": username,
                "smtp_password": password,
                "from_email": username,
                "self_email": username,
            }
        )

    out_dir = WORKSPACE_ROOT / "runs" / f"ethereal-{_utc_stamp()}"

    request = RunRequest(
        date=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        mode="movers",
        region="us",
        source="most-active",
        top=5,
        out_dir=str(out_dir),
        send_email=True,
    )

    artifacts = run_daily_movers(request=request, config=cfg)

    digest_path = Path(artifacts.paths["digest_html"]).resolve()
    webbrowser.open(digest_path.as_uri())

    print(artifacts.model_dump_json(indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise SystemExit(130)
    except Exception as exc:  # noqa: BLE001
        print(f"ethereal_run failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
