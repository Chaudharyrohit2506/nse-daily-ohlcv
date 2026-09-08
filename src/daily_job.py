from datetime import date, timedelta
from .collect import collect

def main():
    # Try today first. If NSE has no session/file, try the previous weekday.
    d = date.today()
    for _ in range(7):
        if d.weekday() < 5:
            try:
                n = collect(d.isoformat())
                print(f"Loaded {n} rows for {d}")
                return
            except FileNotFoundError:
                pass
            except Exception as e:
                print(f"Attempt for {d} failed: {e}")
        d -= timedelta(days=1)

    raise RuntimeError("Could not ingest a recent NSE trading session.")

if __name__ == "__main__":
    main()
