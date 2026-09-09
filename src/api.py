from pathlib import Path
from datetime import date

import pandas as pd
from fastapi import FastAPI, HTTPException, Query

APP_DIR = Path(__file__).resolve().parent.parent
MASTER_FILE = APP_DIR / "data" / "nse_ohlcv_3year_master.parquet"

app = FastAPI(
    title="NSE Historical OHLCV API",
    description="Read-only API for the combined NSE equity and index master dataset.",
    version="1.0.0",
)


def load_master() -> pd.DataFrame:
    if not MASTER_FILE.exists():
        raise HTTPException(
            status_code=503,
            detail="Master dataset is not available.",
        )

    df = pd.read_parquet(MASTER_FILE)

    required = [
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

    missing = [c for c in required if c not in df.columns]

    if missing:
        raise HTTPException(
            status_code=500,
            detail=f"Master dataset missing columns: {missing}",
        )

    df["trade_date"] = pd.to_datetime(
        df["trade_date"],
        errors="coerce",
    )

    return df


def normalize_symbol(symbol: str) -> str:
    return symbol.strip().upper()


@app.get("/")
def root():
    return {
        "service": "NSE Historical OHLCV API",
        "status": "ok",
        "dataset": "data/nse_ohlcv_3year_master.parquet",
    }


@app.get("/health")
def health():
    if not MASTER_FILE.exists():
        return {
            "status": "error",
            "master_exists": False,
        }

    df = load_master()

    return {
        "status": "ok",
        "master_exists": True,
        "rows": int(len(df)),
        "min_date": str(df["trade_date"].min().date()),
        "max_date": str(df["trade_date"].max().date()),
        "unique_dates": int(df["trade_date"].nunique()),
    }


@app.get("/metadata")
def metadata():
    df = load_master()

    return {
        "dataset": "nse_ohlcv_3year_master.parquet",
        "rows": int(len(df)),
        "min_date": str(df["trade_date"].min().date()),
        "max_date": str(df["trade_date"].max().date()),
        "unique_dates": int(df["trade_date"].nunique()),
        "asset_types": {
            str(k): int(v)
            for k, v in df["asset_type"].value_counts().items()
        },
        "columns": list(df.columns),
    }


@app.get("/symbols")
def symbols(
    asset_type: str | None = Query(
        default=None,
        description="EQUITY or INDEX",
    )
):
    df = load_master()

    if asset_type:
        asset_type = asset_type.strip().upper()

        if asset_type not in {"EQUITY", "INDEX"}:
            raise HTTPException(
                status_code=400,
                detail="asset_type must be EQUITY or INDEX.",
            )

        df = df[df["asset_type"] == asset_type]

    values = (
        df["symbol"]
        .dropna()
        .astype(str)
        .drop_duplicates()
        .sort_values()
        .tolist()
    )

    return {
        "count": len(values),
        "asset_type": asset_type,
        "symbols": values,
    }


@app.get("/historical")
def historical(
    symbol: str = Query(
        ...,
        description="NSE symbol or index name",
    ),
    start_date: date | None = Query(
        default=None,
        description="YYYY-MM-DD",
    ),
    end_date: date | None = Query(
        default=None,
        description="YYYY-MM-DD",
    ),
    asset_type: str | None = Query(
        default=None,
        description="EQUITY or INDEX",
    ),
    limit: int = Query(
        default=5000,
        ge=1,
        le=10000,
    ),
):
    df = load_master()

    symbol_input = symbol.strip()

    if not symbol_input:
        raise HTTPException(
            status_code=400,
            detail="symbol cannot be empty.",
        )

    if asset_type:
        asset_type = asset_type.strip().upper()

        if asset_type not in {"EQUITY", "INDEX"}:
            raise HTTPException(
                status_code=400,
                detail="asset_type must be EQUITY or INDEX.",
            )

        df = df[df["asset_type"] == asset_type]

    # Symbol matching is case-insensitive.
    symbol_upper = symbol_input.upper()

    df = df[
        df["symbol"]
        .astype(str)
        .str.strip()
        .str.upper()
        == symbol_upper
    ]

    if df.empty:
        raise HTTPException(
            status_code=404,
            detail=f"No data found for symbol: {symbol_input}",
        )

    if start_date:
        start_ts = pd.Timestamp(start_date)
        df = df[df["trade_date"] >= start_ts]

    if end_date:
        end_ts = pd.Timestamp(end_date)
        df = df[df["trade_date"] <= end_ts]

    if start_date and end_date and start_date > end_date:
        raise HTTPException(
            status_code=400,
            detail="start_date cannot be after end_date.",
        )

    # Always calculate/return chronologically.
    df = df.sort_values(
        ["trade_date"],
        ascending=True,
    )

    # Remove accidental duplicate records.
    df = df.drop_duplicates(
        ["trade_date", "symbol", "asset_type"],
        keep="last",
    )

    total_available = len(df)

    if total_available > limit:
        df = df.tail(limit)

    columns = [
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

    result = df[columns].copy()

    result["trade_date"] = result["trade_date"].dt.strftime(
        "%Y-%m-%d"
    )

    # Convert pandas NA/NaN to JSON null.
    result = result.astype(object).where(
        pd.notna(result),
        None,
    )

    return {
        "symbol": symbol_input,
        "asset_type": asset_type,
        "requested_start_date": (
            str(start_date) if start_date else None
        ),
        "requested_end_date": (
            str(end_date) if end_date else None
        ),
        "returned_rows": len(result),
        "available_rows_after_filters": total_available,
        "truncated": total_available > limit,
        "data": result.to_dict(orient="records"),
    }


@app.get("/latest")
def latest(
    symbol: str = Query(...),
    asset_type: str | None = Query(default=None),
):
    df = load_master()

    if asset_type:
        asset_type = asset_type.strip().upper()

        if asset_type not in {"EQUITY", "INDEX"}:
            raise HTTPException(
                status_code=400,
                detail="asset_type must be EQUITY or INDEX.",
            )

        df = df[df["asset_type"] == asset_type]

    symbol_upper = symbol.strip().upper()

    df = df[
        df["symbol"]
        .astype(str)
        .str.strip()
        .str.upper()
        == symbol_upper
    ]

    if df.empty:
        raise HTTPException(
            status_code=404,
            detail=f"No data found for symbol: {symbol}",
        )

    latest_date = df["trade_date"].max()

    row = (
        df[df["trade_date"] == latest_date]
        .drop_duplicates(
            ["trade_date", "symbol", "asset_type"]
        )
        .iloc[0]
    )

    output = {}

    for column in [
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
    ]:
        value = row[column]

        if pd.isna(value):
            value = None
        elif column == "trade_date":
            value = pd.Timestamp(value).strftime("%Y-%m-%d")
        elif hasattr(value, "item"):
            value = value.item()

        output[column] = value

    return output
