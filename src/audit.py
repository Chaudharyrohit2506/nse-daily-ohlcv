import tomllib
from .db import connect

def main():
    with open("config/settings.toml", "rb") as f:
        cfg = tomllib.load(f)
    con = connect(cfg["database"]["path"])

    queries = {
        "rows": "SELECT COUNT(*) FROM daily_ohlcv",
        "symbols": "SELECT COUNT(DISTINCT symbol) FROM daily_ohlcv",
        "latest_date": "SELECT MAX(trade_date) FROM daily_ohlcv",
        "oldest_date": "SELECT MIN(trade_date) FROM daily_ohlcv",
        "runs_failed": "SELECT COUNT(*) FROM ingestion_runs WHERE status='FAILED'",
        "duplicates": """
            SELECT COUNT(*) FROM (
                SELECT trade_date,symbol,series,COUNT(*) c
                FROM daily_ohlcv
                GROUP BY trade_date,symbol,series
                HAVING c > 1
            )
        """,
    }

    for name, q in queries.items():
        print(f"{name}: {con.execute(q).fetchone()[0]}")

    con.close()

if __name__ == "__main__":
    main()
