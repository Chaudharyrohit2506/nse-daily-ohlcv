import pandas as pd

REQUIRED = ["symbol", "series", "open", "high", "low", "close", "volume"]

def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    mapping = {}
    for c in df.columns:
        x = str(c).strip().upper().replace(" ", "_")
        mapping[c] = x
    df = df.rename(columns=mapping)

    aliases = {
        "SYMBOL": "symbol",
        "SERIES": "series",
        "OPEN_PRICE": "open",
        "HIGH_PRICE": "high",
        "LOW_PRICE": "low",
        "CLOSE_PRICE": "close",
        "PREV_CLOSE": "prev_close",
        "PREV_CLOSE_PRICE": "prev_close",
        "TTL_TRD_QNTY": "volume",
        "TOTTRDQTY": "volume",
        "TOTAL_TURNOVER": "traded_value",
        "TURNOVER_LACS": "traded_value",
        "ISIN": "isin", "TCKRSYMB": "symbol", "SCTYSRS": "series", "OPNPRIC": "open", "HGHPRIC": "high", "LWPRIC": "low", "CLSPRIC": "close", "PRVSCLSGPRIC": "prev_close", "TTLTRADGVOL": "volume", "TTLTRFVAL": "traded_value",
    }

    out = df.rename(columns={k: v for k, v in aliases.items() if k in df.columns})

    missing = [x for x in REQUIRED if x not in out.columns]
    if missing:
        raise ValueError(f"Missing required columns after normalization: {missing}")

    return out

def validate(df: pd.DataFrame, trade_date: str, keep_series=("EQ",)):
    df = normalize_columns(df).copy()
    df["trade_date"] = trade_date
    df["symbol"] = df["symbol"].astype(str).str.strip().str.upper()
    df["series"] = df["series"].astype(str).str.strip().str.upper()

    df = df[df["series"].isin(keep_series)].copy()

    numeric = ["open", "high", "low", "close", "prev_close", "volume", "traded_value"]
    for c in numeric:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")

    errors = []

    for c in ["open", "high", "low", "close", "volume"]:
        errors.append(df[c].notna())

    errors.append(df["open"] > 0)
    errors.append(df["high"] >= df["low"])
    errors.append(df["high"] >= df["open"])
    errors.append(df["high"] >= df["close"])
    errors.append(df["low"] <= df["open"])
    errors.append(df["low"] <= df["close"])
    errors.append(df["volume"] >= 0)

    valid = errors[0]
    for e in errors[1:]:
        valid &= e

    invalid = df.loc[~valid].copy()
    valid_df = df.loc[valid].copy()

    # Deduplicate inside a file. Duplicate keys are not silently averaged.
    dup = valid_df.duplicated(["trade_date", "symbol", "series"], keep=False)
    duplicate_rows = valid_df.loc[dup].copy()
    valid_df = valid_df.loc[~dup].copy()

    return valid_df, invalid, duplicate_rows
