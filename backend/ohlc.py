"""
CSV / TXT upload + OHLC export.

Accepts an uploaded CSV or TXT listing tickers (one per line, a single
'symbol' column, or whitespace/semicolon-separated), fetches daily OHLC for
each from yfinance, then emits a single combined CSV.
"""

from __future__ import annotations

import io
import re
from typing import Iterable, List, Tuple

import pandas as pd
import yfinance as yf

from .symbols import normalize_symbol

_RANGE_TO_PERIOD = {
    "1mo": "1mo",
    "1y": "1y",
    "5y": "5y",
    "10y": "10y",
    "20y": "max",  # yfinance only goes back to listing; "max" honours that
}


_HEADER_WORDS = {"symbol", "ticker", "tickers", "stock", "stocks", "scrip", "nse", "name"}


def parse_tickers(raw: bytes) -> List[str]:
    """Pull tickers out of an uploaded CSV or TXT blob.

    Accepted shapes:
      - one ticker per line (no header) — .csv or .txt
      - a CSV with a header row that contains "symbol" / "ticker" / "stock"
        (we use the first column when no recognised header name is present)
      - a free-form .txt list separated by spaces, tabs, newlines or semicolons
        (e.g. "RELIANCE TCS INFY" or "NSE:RELIANCE; NSE:TCS")
    """
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        try:
            text = raw.decode("latin-1")
        except UnicodeDecodeError as exc:
            raise ValueError("Could not decode the uploaded file as text.") from exc

    text = text.strip()
    if not text:
        return []

    tokens: List[str] = []
    if "," in text:
        # CSV-like: take the first cell of every row so an extra "name"
        # column (which may contain spaces) is ignored.
        for line in io.StringIO(text):
            v = line.split(",")[0].strip().strip('"').strip("'")
            if v:
                tokens.append(v)
    else:
        # Plain list (typical .txt): split on whitespace, newlines and
        # semicolons. Ticker symbols never contain those, but may contain
        # ':', '.', '&' or '-', which we deliberately keep intact.
        for tok in re.split(r"[\s;]+", text):
            tok = tok.strip().strip('"').strip("'")
            if tok:
                tokens.append(tok)

    if not tokens:
        return []

    # If the first token looks like a header (matches a known column name),
    # drop it. We do this ourselves because csv.Sniffer guesses poorly on
    # very short files.
    if tokens[0].lower() in _HEADER_WORDS:
        tokens = tokens[1:]

    # de-dupe while preserving order
    seen = set()
    unique = []
    for t in tokens:
        k = t.upper()
        if k not in seen:
            seen.add(k)
            unique.append(t)
    return unique


# yfinance is fetched in blocks of this many tickers per batched request so
# arbitrarily large uploads stay manageable (and avoid one giant request).
_BLOCK_SIZE = 200

_OHLCV = ["Open", "High", "Low", "Close", "Volume"]


def _format_history(df: pd.DataFrame) -> pd.DataFrame:
    """Normalise a raw OHLC frame to columns: Date, Open, High, Low, Close, Volume."""
    if df is None or df.empty:
        return pd.DataFrame()
    if not all(c in df.columns for c in _OHLCV):
        return pd.DataFrame()
    df = df[_OHLCV].copy()
    df = df.dropna(how="all")
    if df.empty:
        return pd.DataFrame()
    df.index = df.index.tz_localize(None) if df.index.tz is not None else df.index
    df.reset_index(inplace=True)
    df.rename(columns={"index": "Date", "Date": "Date"}, inplace=True)
    df["Date"] = pd.to_datetime(df["Date"]).dt.strftime("%Y-%m-%d")
    return df


def _download_ohlc(symbol_yf: str, period: str) -> pd.DataFrame:
    """Single-ticker download — used as a fallback when a batch drops a symbol."""
    try:
        df = yf.Ticker(symbol_yf).history(period=period, interval="1d", auto_adjust=False)
    except Exception:
        return pd.DataFrame()
    return _format_history(df)


def _download_block(symbols_yf: List[str], period: str) -> pd.DataFrame:
    """Batched multi-ticker download. Returns the raw (MultiIndex) frame, or empty."""
    if not symbols_yf:
        return pd.DataFrame()
    try:
        return yf.download(
            symbols_yf,
            period=period,
            interval="1d",
            auto_adjust=False,
            group_by="ticker",
            threads=True,
            progress=False,
        )
    except Exception:
        return pd.DataFrame()


def _chunk(items: List, size: int):
    for i in range(0, len(items), size):
        yield items[i : i + size]


def build_ohlc_csv(user_tickers: Iterable[str], range_key: str) -> Tuple[str, str]:
    period = _RANGE_TO_PERIOD.get(range_key, "1y")

    # 1) Resolve every requested ticker first, de-duping by NSE symbol so the
    #    same stock isn't fetched twice. Order is preserved.
    resolved = []  # list of Symbol
    seen_nse = set()
    unresolved: List[str] = []
    for raw_ticker in user_tickers:
        sym = normalize_symbol(raw_ticker)
        if sym is None:
            unresolved.append(raw_ticker)
            continue
        if sym.nse in seen_nse:
            continue
        seen_nse.add(sym.nse)
        resolved.append(sym)

    # 2) Fetch in blocks of _BLOCK_SIZE using a single batched request per block,
    #    falling back to a per-ticker download when the batch misses a symbol.
    frames: List[pd.DataFrame] = []
    resolved_count = 0
    empty: List[str] = []

    for block in _chunk(resolved, _BLOCK_SIZE):
        batch = _download_block([s.yf for s in block], period)
        batch_has_cols = isinstance(batch.columns, pd.MultiIndex) and not batch.empty
        for sym in block:
            df = pd.DataFrame()
            if batch_has_cols and sym.yf in batch.columns.get_level_values(0):
                df = _format_history(batch[sym.yf])
            if df.empty:
                # batch missed it (or whole batch failed) — try once on its own
                df = _download_ohlc(sym.yf, period)
            if df.empty:
                empty.append(sym.nse)
                continue
            df.insert(0, "Symbol", sym.nse)
            frames.append(df)
            resolved_count += 1

    if frames:
        combined = pd.concat(frames, ignore_index=True)
        combined = combined[["Symbol", "Date", "Open", "High", "Low", "Close", "Volume"]]
        for col in ("Open", "High", "Low", "Close"):
            combined[col] = combined[col].round(2)
        combined["Volume"] = combined["Volume"].fillna(0).astype("int64")
        csv_text = combined.to_csv(index=False)
    else:
        csv_text = "Symbol,Date,Open,High,Low,Close,Volume\n"

    summary = (
        f"resolved={resolved_count}; "
        f"unresolved={len(unresolved)}; "
        f"empty={len(empty)}; "
        f"range={range_key}"
    )
    return csv_text, summary
