import sqlite3
from pathlib import Path
from datetime import datetime, timezone

SCHEMA = """
CREATE TABLE IF NOT EXISTS daily_ohlcv (
    trade_date TEXT NOT NULL,
    symbol TEXT NOT NULL,
    series TEXT NOT NULL,
    isin TEXT,
    open REAL NOT NULL,
    high REAL NOT NULL,
    low REAL NOT NULL,
    close REAL NOT NULL,
    prev_close REAL,
    volume INTEGER NOT NULL,
    traded_value REAL,
    source TEXT NOT NULL,
    ingested_at TEXT NOT NULL,
    PRIMARY KEY (trade_date, symbol, series)
);

CREATE INDEX IF NOT EXISTS idx_ohlcv_symbol_date
ON daily_ohlcv(symbol, trade_date);

CREATE INDEX IF NOT EXISTS idx_ohlcv_date
ON daily_ohlcv(trade_date);

CREATE TABLE IF NOT EXISTS ingestion_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    trade_date TEXT NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    status TEXT NOT NULL,
    rows_loaded INTEGER DEFAULT 0,
    message TEXT
);

CREATE TABLE IF NOT EXISTS securities (
    symbol TEXT PRIMARY KEY,
    isin TEXT,
    company_name TEXT,
    series TEXT,
    first_seen_date TEXT,
    last_seen_date TEXT,
    status TEXT DEFAULT 'ACTIVE'
);
"""

def connect(db_path: str):
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(db_path)
    con.execute("PRAGMA journal_mode=WAL;")
    con.executescript(SCHEMA)
    return con

def now_utc():
    return datetime.now(timezone.utc).isoformat()
