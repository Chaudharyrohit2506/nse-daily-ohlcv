# NSE Daily OHLCV Repository

Automated repository for NSE equity daily OHLCV data.

## What it stores

One row per NSE security per trading session:

- `trade_date`
- `symbol`
- `series`
- `isin`
- `open`
- `high`
- `low`
- `close`
- `prev_close`
- `volume`
- `traded_value`
- `source`
- `ingested_at`

The primary data source is NSE's official CM UDiFF Common Bhavcopy Final archive.

NSE currently exposes the UDiFF Common Bhavcopy Final in its Equity reports and also provides security-wise historical price/volume downloads. The repository is designed around the bulk daily bhavcopy because one file can populate the whole market.

## Architecture

```text
NSE official daily UDiFF Bhavcopy
              |
              v
       download_daily.py
              |
              v
       validation.py
              |
              v
          SQLite DB
              |
              +--> CSV/Parquet exports
              |
              +--> your stock-analysis engine
```

## Important scope

This project is for NSE Capital Market securities. The default collector keeps equity series (`EQ`) and can be extended for ETFs/REITs/INVITs/other series.

It does NOT invent missing prices. If NSE did not publish a valid row, the row remains missing and is reported.

## 1. Install

Python 3.11+ is recommended.

```bash
python -m venv .venv
```

Windows:
```bash
.venv\Scripts\activate
```

macOS/Linux:
```bash
source .venv/bin/activate
```

Then:

```bash
pip install -r requirements.txt
```

## 2. Initialize the database

```bash
python -m src.init_db
```

## 3. Test a single trading day

Example:

```bash
python -m src.collect --date 2026-09-08
```

The collector will:

1. Download the NSE UDiFF daily archive.
2. Extract the CSV.
3. Normalize column names.
4. Keep the required equity series.
5. Validate OHLCV.
6. Upsert rows into SQLite.
7. Write a run log.

## 4. Build one year of history

```bash
python -m src.backfill --days 370
```

The script skips weekends and records failures for NSE holidays/non-trading days.

A safer production approach is to start with a smaller test:

```bash
python -m src.backfill --days 20
```

Then run the full backfill.

## 5. Check the database

```bash
python -m src.audit
```

This reports:

- latest trading date
- number of symbols
- number of rows
- duplicates
- invalid OHLC
- missing expected rows
- ingestion failures

## 6. Daily 5 PM job

The repository includes a daily runner:

```bash
python -m src.daily_job
```

It automatically determines the previous/current expected trading date and attempts the NSE download.

### Windows Task Scheduler

Create a task:

- Trigger: Daily
- Time: 5:00 PM
- Action: Start a program
- Program: `C:\path\to\repo\.venv\Scripts\python.exe`
- Arguments: `-m src.daily_job`
- Start in: `C:\path\to\repo`

### Linux / VPS / GitHub runner

Use cron/systemd or GitHub Actions. See `.github/workflows/daily.yml`.

## 7. Data retention

The collector supports rolling retention:

```bash
python -m src.retention --days 370
```

Run this after the daily ingestion. Keeping ~370 calendar days gives enough room for approximately one year of trading sessions.

## 8. Repository layout

```text
nse_daily_ohlcv_repository/
├── .github/
│   └── workflows/
│       └── daily.yml
├── config/
│   └── settings.toml
├── data/
│   ├── raw/
│   ├── exports/
│   └── nse_ohlcv.sqlite3
├── logs/
├── src/
│   ├── __init__.py
│   ├── nse_client.py
│   ├── validation.py
│   ├── db.py
│   ├── init_db.py
│   ├── collect.py
│   ├── backfill.py
│   ├── daily_job.py
│   ├── retention.py
│   └── audit.py
├── .gitignore
├── requirements.txt
└── README.md
```

## Data-source policy

Primary:
- NSE official reports / UDiFF Common Bhavcopy

Secondary:
- only if the primary NSE file is unavailable, and any fallback must be explicitly logged.

Do not silently replace NSE data with Yahoo/other feeds.

## GitHub

```bash
git init
git add .
git commit -m "Initial NSE OHLCV repository"
git branch -M main
git remote add origin <YOUR_GITHUB_REPOSITORY_URL>
git push -u origin main
```

Do NOT commit the SQLite database if you plan to generate it on a server/GitHub runner. Keep `data/nse_ohlcv.sqlite3` in `.gitignore` unless you specifically want the database versioned.

## Next production upgrades

- PostgreSQL instead of SQLite
- NSE security master table
- corporate-action adjusted price layer
- delivery quantity / delivery percentage
- index membership snapshots
- sector mapping
- retry/backoff
- alerting when NSE data is missing
- data-quality score
- Parquet partitioning for faster research
