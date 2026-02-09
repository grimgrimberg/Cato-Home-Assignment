from __future__ import annotations

import json

from daily_movers.adapters.uipath import run_daily_movers


def main() -> None:
    result = run_daily_movers(
        out_dir="runs/uipath-smoke",
        date="2026-02-09",
        mode="movers",
        region="us",
        source="most-active",
        top="5",
        send_email="false",
    )
    print(json.dumps(result, indent=2, ensure_ascii=True))


if __name__ == "__main__":
    main()
