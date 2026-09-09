from pathlib import Path
from datetime import timedelta
import re
import pandas as pd

MASTER_FILE = Path("data/nse_ohlcv_3year_master.parquet")
CHATGPT_DIR = Path("data/chatgpt")
EQUITY_DIR = CHATGPT_DIR / "equity"
INDEX_DIR = CHATGPT_DIR / "index"
MANIFEST_FILE = CHATGPT_DIR / "symbol_index.csv"

REQUIRED_COLUMNS = [
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


def safe_filename(symbol):
    return re.sub(r"[^A-Za-z0-9._-]", "_", str(symbol))


def write_if_changed(df, path):
    content = df.to_csv(index=False)
    if path.exists():
        if path.read_text(encoding="utf-8") == content:
            return False
    path.write_text(content, encoding="utf-8")
    return True


def main():
    if not MASTER_FILE.exists():
        raise FileNotFoundError(f"Missing master dataset: {MASTER_FILE}")

    df = pd.read_parquet(MASTER_FILE)

    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns: {missing}")

    df["trade_date"] = pd.to_datetime(df["trade_date"]).dt.date
    df["symbol"] = df["symbol"].astype(str)
    df["asset_type"] = df["asset_type"].astype(str)

    latest_date = max(df["trade_date"])
    start_date = latest_date - timedelta(days=1095)

    df = df[
        (df["trade_date"] >= start_date)
        & (df["trade_date"] <= latest_date)
    ].copy()

    EQUITY_DIR.mkdir(parents=True, exist_ok=True)
    INDEX_DIR.mkdir(parents=True, exist_ok=True)

    changed = 0
    total_files = 0

    manifest_rows = []

    for asset_type, output_dir in [
        ("EQUITY", EQUITY_DIR),
        ("INDEX", INDEX_DIR),
    ]:
        subset = df[df["asset_type"] == asset_type]

        for symbol, group in subset.groupby("symbol", sort=True):
            filename = safe_filename(symbol) + ".csv"
            path = output_dir / filename

            group = group.sort_values("trade_date", ascending=False)

            output = group[REQUIRED_COLUMNS].copy()
            output["trade_date"] = output["trade_date"].astype(str)

            if write_if_changed(output, path):
                changed += 1

            total_files += 1

            manifest_rows.append({
                "symbol": symbol,
                "asset_type": asset_type,
                "file": str(path.relative_to(CHATGPT_DIR)).replace("\\", "/"),
                "start_date": str(group["trade_date"].min()),
                "end_date": str(group["trade_date"].max()),
                "rows": len(group),
            })

    # Remove stale CSV files
    valid_equity = {
        safe_filename(s) + ".csv"
        for s in df.loc[df["asset_type"] == "EQUITY", "symbol"].unique()
    }
    valid_index = {
        safe_filename(s) + ".csv"
        for s in df.loc[df["asset_type"] == "INDEX", "symbol"].unique()
    }

    for path in EQUITY_DIR.glob("*.csv"):
        if path.name not in valid_equity:
            path.unlink()
            changed += 1

    for path in INDEX_DIR.glob("*.csv"):
        if path.name not in valid_index:
            path.unlink()
            changed += 1

    manifest = pd.DataFrame(manifest_rows).sort_values(
        ["asset_type", "symbol"]
    )

    manifest.to_csv(MANIFEST_FILE, index=False)

    print("CHATGPT CSV BUILD COMPLETE")
    print(f"Latest date: {latest_date}")
    print(f"Rolling start: {start_date}")
    print(f"Total CSV files: {total_files}")
    print(f"Files changed/removed: {changed}")
    print(f"Manifest: {MANIFEST_FILE}")


if __name__ == "__main__":
    main()
