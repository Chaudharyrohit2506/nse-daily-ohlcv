import argparse
import subprocess
import sys
from datetime import date, timedelta

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=370)
    args = parser.parse_args()

    d = date.today() - timedelta(days=args.days)
    end = date.today()

    while d <= end:
        if d.weekday() < 5:
            cmd = [sys.executable, "-m", "src.collect", "--date", d.isoformat()]
            result = subprocess.run(cmd)
            if result.returncode != 0:
                print(f"FAILED/NO FILE: {d.isoformat()}")
        d += timedelta(days=1)

if __name__ == "__main__":
    main()
