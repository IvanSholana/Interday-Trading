from __future__ import annotations

from pathlib import Path

import pandas as pd


def normalize_ticker(raw_ticker: str) -> str | None:
    ticker = raw_ticker.strip().upper()
    if not ticker or ticker.startswith("#"):
        return None
    if "#" in ticker:
        ticker = ticker.split("#", 1)[0].strip()
        if not ticker:
            return None

    if ticker.endswith(".JK"):
        base = ticker[:-3]
    else:
        base = ticker

    if not base or not base.replace("-", "").replace("_", "").isalnum():
        raise ValueError(f"Invalid ticker: {raw_ticker!r}")

    return f"{base}.JK"


def load_tickers(file_path: str | Path) -> list[str]:
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"Ticker file not found: {path}")

    if path.suffix.lower() == ".csv":
        df = pd.read_csv(path)
        if df.empty:
            return []
        source = df["ticker"] if "ticker" in df.columns else df.iloc[:, 0]
        raw_tickers = source.dropna().astype(str).tolist()
    else:
        raw_tickers = path.read_text(encoding="utf-8").splitlines()

    tickers: set[str] = set()
    for raw_ticker in raw_tickers:
        ticker = normalize_ticker(raw_ticker)
        if ticker:
            tickers.add(ticker)

    return sorted(tickers)
