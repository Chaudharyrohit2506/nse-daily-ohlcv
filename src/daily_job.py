from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from .collect import collect

IST = ZoneInfo("Asia/Kolkata")


def main():
    today = datetime.now(IST).date()
    parquet = Path("data/exports") / f"{today:%Y-%m-%d}.parquet"

    # Idempotency: if today's session is already stored, do nothing.
    if parquet.exists():
        print(f"Already collected: {today} — nothing to do.")
        return

    # Weekends have no NSE equity session.
    if today.weekday() >= 5:
        print(f"No NSE session today: {today} (weekend).")
        return

    try:
        n = collect(today.isoformat())
        print(f"Loaded {n} rows for {today}")
    except FileNotFoundError:
        # NSE may not have published the file yet, or today may be a holiday.
        # Exit successfully so the next scheduled retry can try again.
        print(f"No NSE bhavcopy available yet for {today}.")
        return


if __name__ == "__main__":
    main()
