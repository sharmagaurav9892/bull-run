"""Price-history series for the chart on the single-stock view."""

from __future__ import annotations

from typing import Dict, Optional

import pandas as pd
import yfinance as yf

from .cache import TTLCache
from .symbols import normalize_symbol

_chart_cache = TTLCache(ttl_seconds=600)

_RANGES = {
    "1d":  ("5d",   "5m"),
    "1w":  ("1mo",  "30m"),
    "1m":  ("3mo",  "1d"),
    "1y":  ("1y",   "1d"),
    "5y":  ("5y",   "1wk"),
}


def get_return_series(user_input: str, range_key: str) -> Optional[Dict]:
    sym = normalize_symbol(user_input)
    if sym is None:
        return None
    key = (sym.yf, range_key)
    hit = _chart_cache.get(key)
    if hit is not None:
        return hit

    period, interval = _RANGES.get(range_key, _RANGES["1y"])

    try:
        df = yf.Ticker(sym.yf).history(period=period, interval=interval, auto_adjust=False)
    except Exception:
        return None
    if df is None or df.empty:
        return None

    # Clip the daily window to the requested range for cleaner charts.
    if range_key == "1d":
        df = df[df.index.date == df.index.date.max()]
    elif range_key == "1w":
        cutoff = df.index.max() - pd.Timedelta(days=7)
        df = df[df.index >= cutoff]
    elif range_key == "1m":
        cutoff = df.index.max() - pd.Timedelta(days=30)
        df = df[df.index >= cutoff]

    closes = df["Close"].dropna()
    if closes.empty:
        return None

    base = float(closes.iloc[0])
    series = [
        {
            "t": ts.isoformat(),
            "price": float(p),
            "ret_pct": (float(p) / base - 1.0) * 100.0 if base else 0.0,
        }
        for ts, p in closes.items()
    ]

    out = {
        "symbol": sym.nse,
        "range": range_key,
        "interval": interval,
        "base_price": base,
        "last_price": float(closes.iloc[-1]),
        "total_return_pct": (float(closes.iloc[-1]) / base - 1.0) * 100.0 if base else 0.0,
        "series": series,
    }
    _chart_cache.set(key, out)
    return out
