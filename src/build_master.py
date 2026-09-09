from datetime import date, timedelta
from pathlib import Path
import io
import time

import pandas as pd
import requests

START_DATE = date(2023, 9, 8)
END_DATE = date(2026, 9, 8)

INDEX_DIR = Path("data/index_exports")
EQUITY_DIR = Path("data/exports")
MASTER_FILE = Path("data/nse_ohlcv_3year_master.parquet")

INDEX_DIR.mkdir(parents=True, exist_ok=True)

INDEX_URL = (
    "https://nsearchives.nseindia.com/content/indices/"
    "ind_close_all_{date}.csv"
)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/140.0.0.0 Safari/537.36"
    ),
    "Accept": "text/csv,text/plain,*/*",
    "Referer": "https://www.nseindia.com/",
}


def get_session():
    s = requests.Session()
    s.headers.update(HEADERS)

    # Establish NSE session/cookies first.
    try:
        s.get("https://www.nseindia.com/", timeout=30)
    except requests.RequestException:
        pass

    return s


def download_index_file(session, d):
    filename = f"ind_close_all_{d:%d%m%Y}.csv"
    path = INDEX_DIR / filename

    if path.exists() and path.stat().st_size > 100:
        return path

    url = INDEX_URL.format(date=d.strftime("%d%m%Y"))

    for attempt in range(4):
        try:
            r = session.get(url, timeout=45)

            if r.status_code == 200 and len(r.content) > 100:
                path.write_bytes(r.content)
                return path

            if r.status_code in (403, 429):
                time.sleep(5 * (attempt + 1))
            else:
                time.sleep(2)

        except requests.RequestException:
            time.sleep(3 * (attempt + 1))

    return None


def normalize_index_file(path):
    if path is None:
        return pd.DataFrame()

    try:
        df = pd.read_csv(path)
    except Exception:
        return pd.DataFrame()

    df.columns = [
        str(c).strip().lower().replace(" ", "_")
        for c in df.columns
    ]

    # Normalize common NSE index-column names.
    rename = {
        "index_name": "symbol",
        "index_name_": "symbol",
        "index_date": "trade_date",
        "date": "trade_date",
        "open_index_value": "open",
        "high_index_value": "high",
        "low_index_value": "low",
        "closing_index_value": "close",
        "close_index_value": "close",
        "previous_closing_value": "prev_close",
        "prev_close": "prev_close",
        "points_change": "points_change",
        "change": "pct_change",
        "percent_change": "pct_change",
        "volume": "volume",
        "turnover": "traded_value",
    }

    df = df.rename(columns={k: v for k, v in rename.items() if k in df.columns})

    if "symbol" not in df.columns:
        return pd.DataFrame()

    # If the file doesn't carry its own date, derive it from filename.
    if "trade_date" not in df.columns:
        try:
            d = pd.to_datetime(
                path.stem.replace("ind_close_all_", ""),
                format="%d%m%Y"
            ).date()
            df["trade_date"] = d
        except Exception:
            return pd.DataFrame()

    df["trade_date"] = pd.to_datetime(
        df["trade_date"], format="%d-%m-%Y", errors="coerce"
    ).dt.date

    df["symbol"] = df["symbol"].astype(str).str.strip()

    # Remove blank/index-summary rows.
    df = df[
        df["symbol"].notna()
        & (df["symbol"] != "")
        & (df["symbol"].str.lower() != "nan")
    ].copy()

    # Standard master schema.
    for col in [
        "open", "high", "low", "close",
        "prev_close", "volume", "traded_value"
    ]:
        if col not in df.columns:
            df[col] = pd.NA

    df["asset_type"] = "INDEX"
    df["series"] = pd.NA
    df["isin"] = pd.NA

    return df[
        [
            "trade_date",
            "symbol",
            "asset_type",
            "series",
            "isin",
            "open",
            "high",
            "low",
            "close",
            "prev_close",
            "volume",
            "traded_value",
        ]
    ]


def collect_indices():
    session = get_session()

    current = START_DATE
    downloaded = 0
    missing = 0

    while current <= END_DATE:
        if current.weekday() < 5:
            path = download_index_file(session, current)

            if path:
                downloaded += 1
            else:
                missing += 1

            if (downloaded + missing) % 25 == 0:
                print(
                    f"Index files checked: "
                    f"{downloaded + missing} | "
                    f"downloaded: {downloaded} | "
                    f"missing: {missing}"
                )

            time.sleep(1.1)

        current += timedelta(days=1)

    print()
    print("INDEX DOWNLOAD COMPLETE")
    print(f"Downloaded/available: {downloaded}")
    print(f"Missing/unavailable: {missing}")


def load_equities():
    files = sorted(EQUITY_DIR.glob("*.parquet"))

    if not files:
        raise RuntimeError("No equity Parquet files found.")

    frames = []

    for path in files:
        df = pd.read_parquet(path)

        if df.empty:
            continue

        df["asset_type"] = "EQUITY"

        frames.append(
            df[
                [
                    "trade_date",
                    "symbol",
                    "asset_type",
                    "series",
                    "isin",
                    "open",
                    "high",
                    "low",
                    "close",
                    "prev_close",
                    "volume",
                    "traded_value",
                ]
            ]
        )

    if not frames:
        raise RuntimeError("Equity Parquet files contained no rows.")

    return pd.concat(frames, ignore_index=True)


def load_indices():
    files = sorted(INDEX_DIR.glob("ind_close_all_*.csv"))

    frames = []

    for path in files:
        df = normalize_index_file(path)

        if not df.empty:
            frames.append(df)

    if not frames:
        raise RuntimeError(
            "No usable index files found. "
            "Run the index download first."
        )

    return pd.concat(frames, ignore_index=True)


def build_master():
    print("Loading equity data...")
    equities = load_equities()

    print(f"Equity rows: {len(equities):,}")

    print("Loading index data...")
    indices = load_indices()

    print(f"Index rows: {len(indices):,}")

    master = pd.concat(
        [equities, indices],
        ignore_index=True
    )

    master["trade_date"] = pd.to_datetime(
        master["trade_date"], format="mixed", dayfirst=True, errors="coerce"
    )

    master = master[
        master["trade_date"].notna()
        & master["symbol"].notna()
    ].copy()

    # Normalize symbols.
    master["symbol"] = (
        master["symbol"]
        .astype(str)
        .str.strip()
    )

    # Normalize mixed equity/index column types before PyArrow export.
    text_cols = ["symbol", "asset_type", "series", "isin"]
    for col in text_cols:
        master[col] = master[col].astype("string")

    numeric_cols = [
        "open", "high", "low", "close",
        "prev_close", "volume", "traded_value"
    ]
    for col in numeric_cols:
        master[col] = pd.to_numeric(master[col], errors="coerce")

    # Normalize mixed equity/index column types before PyArrow export.
    text_cols = ["symbol", "asset_type", "series", "isin"]
    for col in text_cols:
        master[col] = master[col].astype("string")

    numeric_cols = [
        "open", "high", "low", "close",
        "prev_close", "volume", "traded_value"
    ]
    for col in numeric_cols:
        master[col] = pd.to_numeric(master[col], errors="coerce")

    # Remove exact duplicate records.
    before = len(master)

    master = master.drop_duplicates(
        subset=["trade_date", "symbol", "asset_type"],
        keep="last"
    )

    duplicates_removed = before - len(master)

    # Latest date first, then ticker.
    master = master.sort_values(
        ["trade_date", "asset_type", "symbol"],
        ascending=[False, True, True],
        kind="stable",
    )

    MASTER_FILE.parent.mkdir(parents=True, exist_ok=True)
    master.to_parquet(
        MASTER_FILE,
        index=False,
        engine="pyarrow",
        compression="zstd",
    )

    print()
    print("MASTER DATASET COMPLETE")
    print(f"File: {MASTER_FILE}")
    print(f"Rows: {len(master):,}")
    print(f"Dates: {master['trade_date'].nunique():,}")
    print(f"Unique date/symbol/type: {master[['trade_date','symbol','asset_type']].drop_duplicates().shape[0]:,}")
    print(f"Duplicates removed: {duplicates_removed:,}")
    print(f"First date: {master['trade_date'].min().date()}")
    print(f"Last date: {master['trade_date'].max().date()}")

    print()
    print("SAMPLE:")
    print(
        master[
            [
                "trade_date",
                "symbol",
                "asset_type",
                "open",
                "high",
                "low",
                "close",
            ]
        ].head(20).to_string(index=False)
    )


if __name__ == "__main__":
    import sys

    if len(sys.argv) != 2:
        print("Usage:")
        print("  python -m src.build_master download")
        print("  python -m src.build_master build")
        raise SystemExit(2)

    command = sys.argv[1].lower()

    if command == "download":
        collect_indices()
    elif command == "build":
        build_master()
    else:
        raise SystemExit(f"Unknown command: {command}")
