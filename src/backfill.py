import io
import time
import zipfile
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import requests
import tomllib

from .collect import collect, load_into_db
from .db import connect

UDIFF_START = date(2024, 7, 8)
START_DATE = date(2023, 9, 8)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/140 Safari/537.36",
    "Accept": "*/*",
    "Referer": "https://www.nseindia.com/",
    "Connection": "keep-alive",
}


def existing_sessions():
    export_dir = Path("data/exports")
    export_dir.mkdir(parents=True, exist_ok=True)
    return {
        p.stem
        for p in export_dir.glob("*.parquet")
        if len(p.stem) == 10 and p.stem[4] == "-" and p.stem[7] == "-"
    }


def legacy_url(d):
    month = d.strftime("%b").upper()
    return (
        f"https://archives.nseindia.com/content/historical/EQUITIES/"
        f"{d:%Y}/{month}/cm{d:%d}{month}{d:%Y}bhav.csv.zip"
    )

def collect_legacy(d, cfg):
    url = legacy_url(d)

    session = requests.Session()
    session.headers.update(HEADERS)

    last_error = None

    for attempt in range(1, 5):
        try:
            r = session.get(url, timeout=45)

            if r.status_code == 404:
                raise FileNotFoundError(url)

            r.raise_for_status()

            if not r.content[:2] == b"PK":
                raise ValueError("NSE legacy response is not a ZIP archive")

            with zipfile.ZipFile(io.BytesIO(r.content)) as z:
                csv_names = [n for n in z.namelist() if n.lower().endswith(".csv")]
                if not csv_names:
                    raise ValueError("No CSV found inside legacy NSE archive")
                raw_csv = z.read(csv_names[0])

            raw = pd.read_csv(io.BytesIO(raw_csv))

            from .validation import validate

            valid, invalid, duplicates = validate(
                raw,
                d.isoformat(),
                tuple(cfg["collection"]["keep_series"]),
            )

            if len(valid) == 0:
                raise ValueError("No valid equity rows found")

            con = connect(cfg["database"]["path"])
            try:
                loaded = load_into_db(con, valid, "NSE_LEGACY_BHAVCOPY")

                export_dir = Path(cfg["collection"]["export_dir"])
                export_dir.mkdir(parents=True, exist_ok=True)

                export_cols = [
                    "trade_date", "symbol", "series", "isin",
                    "open", "high", "low", "close",
                    "prev_close", "volume", "traded_value"
                ]

                valid[export_cols].to_parquet(
                    export_dir / f"{d:%Y-%m-%d}.parquet",
                    index=False,
                )
            finally:
                con.close()

            print(
                f"URL={url}; raw={len(raw)}; valid={len(valid)}; "
                f"invalid={len(invalid)}; duplicate_rows={len(duplicates)}"
            )

            return loaded

        except Exception as exc:
            last_error = exc
            if attempt < 4:
                time.sleep(2 ** attempt)

    raise last_error


def main():
    with open("config/settings.toml", "rb") as f:
        cfg = tomllib.load(f)

    sessions = existing_sessions()

    today = datetime.now(ZoneInfo("Asia/Kolkata")).date()
    end_date = today - timedelta(days=1)

    # Exactly three calendar years of history.
    start_date = START_DATE

    print(f"Existing Parquet sessions: {len(sessions)}")
    print(f"Target range: {start_date} -> {end_date}")

    current = end_date
    checked = 0
    added = 0
    failed = 0

    while current >= start_date:
        date_str = current.isoformat()
        checked += 1

        if current.weekday() >= 5:
            current -= timedelta(days=1)
            continue

        if date_str in sessions:
            current -= timedelta(days=1)
            continue

        print(f"[{checked}] Collecting {date_str}...")

        try:
            if current >= UDIFF_START:
                collect(date_str)
            else:
                collect_legacy(current, cfg)

            output = Path(cfg["collection"]["export_dir"]) / f"{date_str}.parquet"

            if output.exists():
                sessions.add(date_str)
                added += 1
                print(f"SUCCESS: {date_str} | total sessions={len(sessions)}")

        except FileNotFoundError:
            print(f"NO NSE FILE: {date_str} — likely holiday/no session")

        except Exception as exc:
            failed += 1
            print(f"FAILED: {date_str} — {exc}")

        current -= timedelta(days=1)
        time.sleep(1)

    print()
    print("3-YEAR BACKFILL COMPLETE")
    print(f"Total Parquet sessions: {len(sessions)}")
    print(f"New sessions added: {added}")
    print(f"Failed dates: {failed}")
    print(f"Calendar dates checked: {checked}")


if __name__ == "__main__":
    main()
