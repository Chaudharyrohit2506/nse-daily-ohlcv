import argparse
import tomllib
from datetime import date, timedelta
from .db import connect

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int)
    args = parser.parse_args()

    with open("config/settings.toml", "rb") as f:
        cfg = tomllib.load(f)

    days = args.days or cfg["retention"]["calendar_days"]
    cutoff = date.today() - timedelta(days=days)

    con = connect(cfg["database"]["path"])
    cur = con.execute("DELETE FROM daily_ohlcv WHERE trade_date < ?", (cutoff.isoformat(),))
    con.commit()
    print(f"Deleted {cur.rowcount} rows older than {cutoff}.")
    con.close()

if __name__ == "__main__":
    main()
