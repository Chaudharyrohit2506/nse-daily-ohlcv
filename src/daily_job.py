from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

from .collect import collect

IST = ZoneInfo("Asia/Kolkata")
LOOKBACK_DAYS = 7


def main():
    today = datetime.now(IST).date()
    export_dir = Path("data/exports")
    export_dir.mkdir(parents=True, exist_ok=True)

    # Do not assume the workflow execution date is the NSE trade date.
    # GitHub Actions can be delayed, and NSE files can be published late.
    # Scan recent calendar days so missed sessions are automatically backfilled.
    for offset in range(LOOKBACK_DAYS - 1, -1, -1):
        target = today - timedelta(days=offset)
        parquet = export_dir / f"{target:%Y-%m-%d}.parquet"

        if parquet.exists():
            print(f"Already collected: {target}")
            continue

        if target.weekday() >= 5:
            print(f"No NSE session: {target} (weekend).")
            continue

        try:
            n = collect(target.isoformat())
            print(f"Loaded {n} rows for {target}")
        except FileNotFoundError:
            # 404 means NSE has no archive for this date yet (or it is a holiday).
            print(f"No NSE bhavcopy available for {target}.")
        except requests.RequestException as e:
            # A transient NSE download/network error must not prevent
            # later missing sessions from being attempted.
            print(f"Temporary NSE download failure for {target}: {e}")


if __name__ == "__main__":
    main()
