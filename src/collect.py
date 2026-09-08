import argparse
import tomllib
from datetime import datetime
from pathlib import Path

from .db import connect, now_utc
from .nse_client import download_udiff
from .validation import validate

def load_into_db(con, df, source):
    cols = [
        "trade_date","symbol","series","isin","open","high","low","close",
        "prev_close","volume","traded_value","source","ingested_at"
    ]
    for c in cols:
        if c not in df.columns:
            df[c] = None

    ingested = now_utc()
    rows = []
    for r in df[cols].itertuples(index=False, name=None):
        rows.append((*r[:-1], source, ingested))

    # r already includes source? We rebuild cleanly below.
    rows = []
    for r in df.itertuples(index=False):
        rows.append((
            r.trade_date, r.symbol, r.series, getattr(r, "isin", None),
            float(r.open), float(r.high), float(r.low), float(r.close),
            None if getattr(r, "prev_close", None) is None else float(r.prev_close),
            int(r.volume), None if getattr(r, "traded_value", None) is None else float(r.traded_value),
            source, ingested
        ))

    con.executemany("""
        INSERT INTO daily_ohlcv
        (trade_date,symbol,series,isin,open,high,low,close,prev_close,volume,traded_value,source,ingested_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(trade_date,symbol,series) DO UPDATE SET
            isin=excluded.isin,
            open=excluded.open,
            high=excluded.high,
            low=excluded.low,
            close=excluded.close,
            prev_close=excluded.prev_close,
            volume=excluded.volume,
            traded_value=excluded.traded_value,
            source=excluded.source,
            ingested_at=excluded.ingested_at
    """, rows)

    con.executemany("""
        INSERT INTO securities(symbol,isin,series,first_seen_date,last_seen_date,status)
        VALUES(?,?,?,?,?,'ACTIVE')
        ON CONFLICT(symbol) DO UPDATE SET
            isin=excluded.isin,
            series=excluded.series,
            last_seen_date=excluded.last_seen_date,
            status='ACTIVE'
    """, [
        (r.symbol, getattr(r, "isin", None), r.series, r.trade_date, r.trade_date)
        for r in df.itertuples(index=False)
    ])
    con.commit()
    return len(rows)

def collect(date_str=None):
    with open("config/settings.toml", "rb") as f:
        cfg = tomllib.load(f)

    date_obj = datetime.strptime(date_str, "%Y-%m-%d").date() if date_str else datetime.now().date()
    db_path = cfg["database"]["path"]

    con = connect(db_path)
    started = now_utc()
    con.execute(
        "INSERT INTO ingestion_runs(trade_date,started_at,status) VALUES(?,?,?)",
        (date_obj.isoformat(), started, "RUNNING")
    )
    run_id = con.execute("SELECT last_insert_rowid()").fetchone()[0]
    con.commit()

    try:
        raw, url, csv_name = download_udiff(
            date_obj,
            cfg["nse"]["udiff_url"],
            timeout=cfg["collection"]["timeout_seconds"],
            retries=cfg["collection"]["max_retries"],
            raw_dir=cfg["collection"]["raw_dir"],
        )

        valid, invalid, duplicates = validate(
            raw, date_obj.isoformat(), tuple(cfg["collection"]["keep_series"])
        )

        if len(valid) == 0:
            raise ValueError("No valid equity rows found after validation.")

        loaded = load_into_db(con, valid, "NSE_UDIFF")

        message = (
            f"URL={url}; file={csv_name}; raw={len(raw)}; valid={len(valid)}; "
            f"invalid={len(invalid)}; duplicate_rows={len(duplicates)}"
        )
        con.execute("""
            UPDATE ingestion_runs
            SET finished_at=?, status='SUCCESS', rows_loaded=?, message=?
            WHERE id=?
        """, (now_utc(), loaded, message, run_id))
        con.commit()

        Path(cfg["collection"]["log_dir"]).mkdir(parents=True, exist_ok=True)
        print(message)
        return loaded

    except Exception as e:
        con.execute("""
            UPDATE ingestion_runs
            SET finished_at=?, status='FAILED', message=?
            WHERE id=?
        """, (now_utc(), str(e), run_id))
        con.commit()
        raise
    finally:
        con.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", help="YYYY-MM-DD")
    args = parser.parse_args()
    collect(args.date)
