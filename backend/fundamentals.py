"""
Fundamentals: build the full payload for a single stock.

Wraps yfinance for ratios/financials, augments with computed Piotroski F-score
and Altman Z-score, then adds NSE-sourced sectoral P/E and shareholding.
"""

from __future__ import annotations

import math
import os
import threading
from typing import Any, Dict, Optional

import pandas as pd
import yfinance as yf
from curl_cffi import requests as crequests

from .cache import TTLCache
from .nse import get_index_pe, get_shareholding, sector_index_for
from .symbols import Symbol, normalize_symbol

_fund_cache = TTLCache(ttl_seconds=900)
_ticker_cache: Dict[str, yf.Ticker] = {}


# ---------------------------------------------------------------------------
# yfinance helpers
# ---------------------------------------------------------------------------

# Yahoo's quote/fundamentals endpoint (quoteSummary) is hard to reach from
# datacenter IPs: it requires a crumb+cookie that Yahoo refuses to hand out to
# cloud hosts (Render, Railway, AWS, ...). Two mitigations, both opt-safe:
#   1. Impersonate a real Chrome via curl_cffi so the TLS fingerprint and
#      headers look like a browser rather than a bot.
#   2. Optionally route every Yahoo call through a proxy (YF_PROXY env var).
#      A residential proxy bypasses the IP-based block entirely. Unset locally
#      so local behaviour is unchanged.
_YF_PROXY = os.environ.get("YF_PROXY") or None

# Apply the proxy globally so chart/OHLC calls (prices.py, ohlc.py) route
# through it too, not just the fundamentals fetch below.
if _YF_PROXY:
    try:
        yf.set_config(proxy=_YF_PROXY)
    except Exception:
        pass

_session_lock = threading.Lock()
_yf_session: Optional["crequests.Session"] = None


def _session() -> "crequests.Session":
    global _yf_session
    with _session_lock:
        if _yf_session is None:
            _yf_session = crequests.Session(impersonate="chrome131")
        return _yf_session


def _ticker(symbol_yf: str) -> yf.Ticker:
    t = _ticker_cache.get(symbol_yf)
    if t is None:
        # Proxy is applied globally via yf.set_config above; passing it to the
        # Ticker constructor trips a bug in yfinance 0.2.66. Session carries the
        # Chrome impersonation.
        t = yf.Ticker(symbol_yf, session=_session())
        _ticker_cache[symbol_yf] = t
    return t


def _row(df: Optional[pd.DataFrame], names) -> Optional[pd.Series]:
    """Find a row in a yfinance financial DataFrame by a list of candidate names."""
    if df is None or df.empty:
        return None
    idx_lower = {str(i).lower(): i for i in df.index}
    for n in names:
        key = n.lower()
        if key in idx_lower:
            return df.loc[idx_lower[key]]
    return None


def _safe(v) -> Optional[float]:
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if math.isnan(f) or math.isinf(f):
        return None
    return f


def _pct(v) -> Optional[float]:
    f = _safe(v)
    return f * 100.0 if f is not None else None


# ---------------------------------------------------------------------------
# Piotroski F-score (9 points)
# ---------------------------------------------------------------------------


def _piotroski(t: yf.Ticker) -> Optional[Dict[str, Any]]:
    try:
        income = t.financials                 # annual income statement
        balance = t.balance_sheet              # annual balance sheet
        cashflow = t.cashflow                  # annual cash flow
    except Exception:
        return None

    if income is None or balance is None or cashflow is None:
        return None
    if income.shape[1] < 2 or balance.shape[1] < 2:
        return None

    cur, prev = income.columns[0], income.columns[1]

    def cell(df, names, col):
        s = _row(df, names)
        if s is None or col not in s.index:
            return None
        return _safe(s[col])

    net_income_cur = cell(income, ["Net Income", "Net Income Common Stockholders"], cur)
    net_income_prev = cell(income, ["Net Income", "Net Income Common Stockholders"], prev)
    cfo_cur = cell(cashflow, ["Operating Cash Flow", "Total Cash From Operating Activities"], cur)

    total_assets_cur = cell(balance, ["Total Assets"], cur)
    total_assets_prev = cell(balance, ["Total Assets"], prev)

    long_term_debt_cur = cell(balance, ["Long Term Debt", "Long Term Debt And Capital Lease Obligation"], cur)
    long_term_debt_prev = cell(balance, ["Long Term Debt", "Long Term Debt And Capital Lease Obligation"], prev)

    current_assets_cur = cell(balance, ["Current Assets", "Total Current Assets"], cur)
    current_assets_prev = cell(balance, ["Current Assets", "Total Current Assets"], prev)
    current_liab_cur = cell(balance, ["Current Liabilities", "Total Current Liabilities"], cur)
    current_liab_prev = cell(balance, ["Current Liabilities", "Total Current Liabilities"], prev)

    shares_cur = cell(balance, ["Ordinary Shares Number", "Share Issued", "Common Stock"], cur)
    shares_prev = cell(balance, ["Ordinary Shares Number", "Share Issued", "Common Stock"], prev)

    revenue_cur = cell(income, ["Total Revenue", "Operating Revenue"], cur)
    revenue_prev = cell(income, ["Total Revenue", "Operating Revenue"], prev)
    gross_profit_cur = cell(income, ["Gross Profit"], cur)
    gross_profit_prev = cell(income, ["Gross Profit"], prev)

    def gt(a, b):
        return a is not None and b is not None and a > b

    points = 0
    detail: Dict[str, Optional[bool]] = {}

    roa_cur = (net_income_cur / total_assets_cur) if (net_income_cur is not None and total_assets_cur) else None
    roa_prev = (net_income_prev / total_assets_prev) if (net_income_prev is not None and total_assets_prev) else None

    detail["roa_positive"] = (roa_cur is not None and roa_cur > 0) or None
    if detail["roa_positive"]:
        points += 1

    detail["cfo_positive"] = (cfo_cur is not None and cfo_cur > 0) or None
    if detail["cfo_positive"]:
        points += 1

    detail["roa_growth"] = gt(roa_cur, roa_prev) or None
    if detail["roa_growth"]:
        points += 1

    detail["cfo_gt_ni"] = (cfo_cur is not None and net_income_cur is not None and cfo_cur > net_income_cur) or None
    if detail["cfo_gt_ni"]:
        points += 1

    detail["ltd_decrease"] = (
        long_term_debt_cur is not None
        and long_term_debt_prev is not None
        and long_term_debt_cur < long_term_debt_prev
    ) or None
    if detail["ltd_decrease"]:
        points += 1

    cr_cur = (current_assets_cur / current_liab_cur) if (current_assets_cur and current_liab_cur) else None
    cr_prev = (current_assets_prev / current_liab_prev) if (current_assets_prev and current_liab_prev) else None
    detail["current_ratio_up"] = gt(cr_cur, cr_prev) or None
    if detail["current_ratio_up"]:
        points += 1

    detail["no_new_shares"] = (
        shares_cur is not None and shares_prev is not None and shares_cur <= shares_prev
    ) or None
    if detail["no_new_shares"]:
        points += 1

    gm_cur = (gross_profit_cur / revenue_cur) if (gross_profit_cur and revenue_cur) else None
    gm_prev = (gross_profit_prev / revenue_prev) if (gross_profit_prev and revenue_prev) else None
    detail["gross_margin_up"] = gt(gm_cur, gm_prev) or None
    if detail["gross_margin_up"]:
        points += 1

    at_cur = (revenue_cur / total_assets_cur) if (revenue_cur and total_assets_cur) else None
    at_prev = (revenue_prev / total_assets_prev) if (revenue_prev and total_assets_prev) else None
    detail["asset_turnover_up"] = gt(at_cur, at_prev) or None
    if detail["asset_turnover_up"]:
        points += 1

    return {"score": points, "max": 9, "components": detail}


# ---------------------------------------------------------------------------
# Altman Z-score
# ---------------------------------------------------------------------------


def _altman_z(t: yf.Ticker, market_cap: Optional[float]) -> Optional[Dict[str, Any]]:
    try:
        income = t.financials
        balance = t.balance_sheet
    except Exception:
        return None

    if income is None or balance is None or income.empty or balance.empty:
        return None

    col_b = balance.columns[0]
    col_i = income.columns[0]

    def cell(df, names, col):
        s = _row(df, names)
        if s is None or col not in s.index:
            return None
        return _safe(s[col])

    total_assets = cell(balance, ["Total Assets"], col_b)
    current_assets = cell(balance, ["Current Assets", "Total Current Assets"], col_b)
    current_liab = cell(balance, ["Current Liabilities", "Total Current Liabilities"], col_b)
    retained = cell(balance, ["Retained Earnings"], col_b)
    total_liab = cell(
        balance,
        ["Total Liabilities Net Minority Interest", "Total Liab", "Total Liabilities"],
        col_b,
    )

    ebit = cell(income, ["EBIT", "Operating Income"], col_i)
    revenue = cell(income, ["Total Revenue", "Operating Revenue"], col_i)

    if not total_assets or not total_liab or market_cap is None:
        return None

    working_capital = (current_assets - current_liab) if (current_assets is not None and current_liab is not None) else None

    parts = {
        "A": (working_capital / total_assets) if working_capital is not None else None,
        "B": (retained / total_assets) if retained is not None else None,
        "C": (ebit / total_assets) if ebit is not None else None,
        "D": (market_cap / total_liab) if total_liab else None,
        "E": (revenue / total_assets) if revenue is not None else None,
    }
    if any(v is None for v in parts.values()):
        return None

    z = 1.2 * parts["A"] + 1.4 * parts["B"] + 3.3 * parts["C"] + 0.6 * parts["D"] + 1.0 * parts["E"]
    if z > 2.99:
        zone = "Safe"
    elif z >= 1.81:
        zone = "Grey"
    else:
        zone = "Distress"

    return {"score": round(z, 2), "zone": zone}


# ---------------------------------------------------------------------------
# Return percentages
# ---------------------------------------------------------------------------


def _returns(t: yf.Ticker) -> Dict[str, Optional[float]]:
    try:
        hist = t.history(period="6y", interval="1d", auto_adjust=False)
    except Exception:
        return {"1d": None, "1w": None, "1m": None, "1y": None, "5y": None}
    if hist is None or hist.empty:
        return {"1d": None, "1w": None, "1m": None, "1y": None, "5y": None}

    closes = hist["Close"].dropna()
    if closes.empty:
        return {"1d": None, "1w": None, "1m": None, "1y": None, "5y": None}

    latest = float(closes.iloc[-1])
    last_idx = closes.index[-1]

    def pct_back(days: int) -> Optional[float]:
        target = last_idx - pd.Timedelta(days=days)
        prior = closes[closes.index <= target]
        if prior.empty:
            return None
        prev = float(prior.iloc[-1])
        if prev <= 0:
            return None
        return (latest / prev - 1.0) * 100.0

    return {
        "1d": pct_back(1),
        "1w": pct_back(7),
        "1m": pct_back(30),
        "1y": pct_back(365),
        "5y": pct_back(365 * 5),
    }


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def get_fundamentals(user_input: str) -> Optional[Dict[str, Any]]:
    sym: Optional[Symbol] = normalize_symbol(user_input)
    if sym is None:
        return None

    cache_key = sym.yf
    hit = _fund_cache.get(cache_key)
    if hit is not None:
        return hit

    t = _ticker(sym.yf)

    try:
        info = t.info or {}
    except Exception:
        info = {}

    # Some yfinance versions return an empty info dict on unknown tickers.
    fast = {}
    try:
        fast = dict(t.fast_info or {})
    except Exception:
        pass

    current_price = (
        _safe(info.get("currentPrice"))
        or _safe(info.get("regularMarketPrice"))
        or _safe(fast.get("last_price"))
    )
    market_cap = _safe(info.get("marketCap")) or _safe(fast.get("market_cap"))
    if current_price is None and market_cap is None:
        # Definitely not a recognised NSE ticker.
        return None

    sector = info.get("sector")
    industry = info.get("industry")
    sector_index = sector_index_for(sector, industry)
    sector_pe = get_index_pe(sector_index)

    # ROCE: EBIT / (Total Assets - Current Liabilities)
    roce = None
    try:
        bal = t.balance_sheet
        inc = t.financials
        if bal is not None and not bal.empty and inc is not None and not inc.empty:
            ta = _safe(_row(bal, ["Total Assets"])[bal.columns[0]]) if _row(bal, ["Total Assets"]) is not None else None
            cl = _safe(_row(bal, ["Current Liabilities", "Total Current Liabilities"])[bal.columns[0]]) if _row(bal, ["Current Liabilities", "Total Current Liabilities"]) is not None else None
            ebit = _safe(_row(inc, ["EBIT", "Operating Income"])[inc.columns[0]]) if _row(inc, ["EBIT", "Operating Income"]) is not None else None
            if ta and cl is not None and ebit is not None and (ta - cl) != 0:
                roce = (ebit / (ta - cl)) * 100.0
    except Exception:
        pass

    piotroski = _piotroski(t)
    altman = _altman_z(t, market_cap)
    rets = _returns(t)
    holding = get_shareholding(sym.nse)

    market_cap_cr = (market_cap / 1e7) if market_cap is not None else None

    pe = _safe(info.get("trailingPE"))
    forward_pe = _safe(info.get("forwardPE"))
    peg = _safe(info.get("pegRatio")) or _safe(info.get("trailingPegRatio"))
    roe = _pct(info.get("returnOnEquity"))
    d_to_e = _safe(info.get("debtToEquity"))
    if d_to_e is not None:
        # yfinance returns D/E as a percentage (e.g. 45.3 == 0.453). Normalise.
        d_to_e = d_to_e / 100.0 if d_to_e > 5 else d_to_e

    payload = {
        "input": sym.raw,
        "symbol": sym.nse,
        "yf_symbol": sym.yf,
        "name": info.get("longName") or info.get("shortName") or sym.nse,
        "sector": sector,
        "industry": industry,
        "currency": info.get("currency") or "INR",
        "exchange": info.get("exchange") or "NSI",
        "fundamentals": {
            "current_price": current_price,
            "market_cap_cr": market_cap_cr,
            "pe": pe,
            "forward_pe": forward_pe,
            "sector_pe": sector_pe,
            "sector_index": sector_index,
            "roce": roce,
            "roe": roe,
            "debt_to_equity": d_to_e,
            "peg": peg,
            "piotroski": piotroski,
            "altman_z": altman,
            "shareholding": holding,
        },
        "returns": rets,
    }

    _fund_cache.set(cache_key, payload)
    return payload
