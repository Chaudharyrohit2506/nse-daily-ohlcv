from .db import connect
import tomllib
from pathlib import Path

def main():
    with open("config/settings.toml", "rb") as f:
        cfg = tomllib.load(f)
    con = connect(cfg["database"]["path"])
    con.close()
    print("Database initialized.")

if __name__ == "__main__":
    main()
