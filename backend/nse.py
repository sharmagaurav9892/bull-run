"""
External data fetchers that have to fight anti-scrape protections.

We use curl-cffi (already a transitive dep of yfinance>=0.2.66) for browser
impersonation. NSE's `allIndices` endpoint works fine with plain requests,
but its `quote-equity` endpoint is hard-blocked by Akamai, so for the
shareholding pattern we scrape screener.in (which the original spec called
out as the preferred source).
"""

from __future__ import annotations

import re
import threading
from typing import Dict, List, Optional

import requests
from curl_cffi import requests as crequests

from .cache import TTLCache

_shareholding_cache = TTLCache(ttl_seconds=12 * 3600)
_index_pe_cache = TTLCache(ttl_seconds=3600)
_search_cache = TTLCache(ttl_seconds=3600, max_entries=4096)

_lock = threading.Lock()
_screener_session: Optional["crequests.Session"] = None
_yahoo_session: Optional["crequests.Session"] = None


# Map a Yahoo "sector" to the NSE index whose trailing P/E is the closest
# benchmark. Falls back to NIFTY 50.
_SECTOR_TO_INDEX = {
    "Technology": "NIFTY IT",
    "Financial Services": "NIFTY FINANCIAL SERVICES",
    "Healthcare": "NIFTY PHARMA",
    "Consumer Defensive": "NIFTY FMCG",
    "Consumer Cyclical": "NIFTY CONSUMPTION",
    "Energy": "NIFTY ENERGY",
    "Industrials": "NIFTY INFRA",
    "Basic Materials": "NIFTY METAL",
    "Utilities": "NIFTY ENERGY",
    "Real Estate": "NIFTY REALTY",
    "Communication Services": "NIFTY MEDIA",
    "Auto Manufacturers": "NIFTY AUTO",
    "Auto Parts": "NIFTY AUTO",
    "Banks": "NIFTY BANK",
    "Insurance": "NIFTY FINANCIAL SERVICES",
}


def sector_index_for(sector: Optional[str], industry: Optional[str]) -> str:
    if industry and industry in _SECTOR_TO_INDEX:
        return _SECTOR_TO_INDEX[industry]
    if sector and sector in _SECTOR_TO_INDEX:
        return _SECTOR_TO_INDEX[sector]
    return "NIFTY 50"


# ---------------------------------------------------------------------------
# NSE indices (trailing P/E)
# ---------------------------------------------------------------------------


_NSE_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_0) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.nseindia.com/",
}

_nse_session_cache: Optional[requests.Session] = None


def _nse_session() -> requests.Session:
    global _nse_session_cache
    if _nse_session_cache is None:
        s = requests.Session()
        s.headers.update(_NSE_HEADERS)
        try:
            s.get("https://www.nseindia.com/", timeout=8)
            s.get("https://www.nseindia.com/market-data/live-equity-market", timeout=8)
        except requests.RequestException:
            pass
        _nse_session_cache = s
    return _nse_session_cache


def nse_get(url: str, timeout: int = 10) -> Optional[dict]:
    sess = _nse_session()
    try:
        r = sess.get(url, timeout=timeout)
        if r.status_code == 401:
            globals()["_nse_session_cache"] = None
            sess = _nse_session()
            r = sess.get(url, timeout=timeout)
        if r.status_code != 200:
            return None
        return r.json()
    except (requests.RequestException, ValueError):
        return None


def get_index_pe(index_name: str) -> Optional[float]:
    """Trailing P/E for an NSE index, e.g. 'NIFTY ENERGY'."""
    key = index_name.upper()
    cached = _index_pe_cache.get(key)
    if cached is not None:
        return cached if cached >= 0 else None

    body = nse_get("https://www.nseindia.com/api/allIndices")
    if not body:
        _index_pe_cache.set(key, -1.0)
        return None

    for entry in body.get("data", []) or []:
        if str(entry.get("index", "")).upper() == key:
            try:
                pe = float(entry.get("pe"))
            except (TypeError, ValueError):
                continue
            _index_pe_cache.set(key, pe)
            return pe

    _index_pe_cache.set(key, -1.0)
    return None


# ---------------------------------------------------------------------------
# Screener.in (shareholding pattern)
# ---------------------------------------------------------------------------


def _screener() -> "crequests.Session":
    global _screener_session
    with _lock:
        if _screener_session is None:
            s = crequests.Session(impersonate="chrome131")
            s.headers.update({
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
            })
            _screener_session = s
        return _screener_session


_SHAREHOLDING_LABEL_PAT = re.compile(
    r'<td\s+class="text">\s*<button[^>]*>\s*'
    r'(Promoters|FIIs?|DIIs?|Government|Public|Others)'
    r'(?:&nbsp;|\s)*<span',
    re.IGNORECASE,
)
_SHAREHOLDING_CELL_PAT = re.compile(r"<td[^>]*>\s*([0-9]+(?:\.[0-9]+)?)%\s*</td>")


def _scrape_shareholding(html: str) -> Optional[Dict[str, float]]:
    """Pull the latest-quarter row of the screener.in shareholding table."""
    # Narrow to the shareholding pattern section
    anchor = html.find('id="shareholding"')
    if anchor < 0:
        return None
    section = html[anchor:anchor + 30000]

    # For each row label, grab the *last* percentage cell that follows it
    # before the next labelled row (== latest quarter).
    rows: Dict[str, float] = {}
    matches = list(_SHAREHOLDING_LABEL_PAT.finditer(section))
    for i, m in enumerate(matches):
        label = m.group(1).lower().rstrip("s")  # promoter, fii, dii, government, public, other
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(section)
        cells = _SHAREHOLDING_CELL_PAT.findall(section[start:end])
        if not cells:
            continue
        try:
            # Latest quarter is the last numeric column in the row.
            rows[label] = float(cells[-1])
        except ValueError:
            continue

    if not rows:
        return None

    # Pull the latest quarter label out of the table header for display.
    header_match = re.search(
        r'<table[^>]*data-result-table[^>]*>[\s\S]{0,2000}?<thead[\s\S]*?</thead>',
        section,
    )
    quarter = ""
    if header_match:
        ths = re.findall(r"<th[^>]*>([^<]+)</th>", header_match.group(0))
        if ths:
            quarter = ths[-1].strip()

    return {
        "period": quarter,
        "promoter": rows.get("promoter"),
        "fii": rows.get("fii"),
        "dii": rows.get("dii"),
        "public": rows.get("public"),
        "government": rows.get("government"),
    }


def get_shareholding(symbol_nse: str) -> Optional[Dict[str, float]]:
    """Latest shareholding pattern from screener.in. None on failure."""
    cached = _shareholding_cache.get(symbol_nse)
    if cached is not None:
        return cached if cached else None

    sess = _screener()
    # Try consolidated first (most relevant for diversified businesses);
    # fall back to standalone.
    for url in (
        f"https://www.screener.in/company/{symbol_nse}/consolidated/",
        f"https://www.screener.in/company/{symbol_nse}/",
    ):
        try:
            r = sess.get(url, timeout=12)
        except Exception:
            continue
        if r.status_code != 200:
            continue
        result = _scrape_shareholding(r.text)
        if result:
            _shareholding_cache.set(symbol_nse, result)
            return result

    _shareholding_cache.set(symbol_nse, {})
    return None


# ---------------------------------------------------------------------------
# Yahoo Finance search (autocomplete)
# ---------------------------------------------------------------------------


def _yahoo() -> "crequests.Session":
    global _yahoo_session
    with _lock:
        if _yahoo_session is None:
            s = crequests.Session(impersonate="chrome131")
            s.headers.update({
                "Accept": "application/json, text/plain, */*",
                "Accept-Language": "en-IN,en;q=0.9",
                "Referer": "https://finance.yahoo.com/",
            })
            _yahoo_session = s
        return _yahoo_session


def search_stocks(query: str, limit: int = 8) -> List[Dict]:
    """Autocomplete suggestions for NSE-listed equities.

    Returns a list of {symbol, name, exchange, sector?} dicts. Limited to
    Indian listings (exchange == 'NSI' or symbol ends with '.NS'), with
    BSE as a fallback when no NSE match exists.
    """
    q = (query or "").strip()
    if len(q) < 1:
        return []

    cache_key = q.lower()
    cached = _search_cache.get(cache_key)
    if cached is not None:
        return cached

    sess = _yahoo()

    def _yh(params):
        try:
            r = sess.get(
                "https://query2.finance.yahoo.com/v1/finance/search",
                params=params,
                timeout=6,
            )
            if r.status_code != 200:
                return []
            return r.json().get("quotes", []) or []
        except Exception:
            return []

    base = {
        "q": q,
        "quotesCount": 20,
        "newsCount": 0,
        "enableFuzzyQuery": "true",
        "researchReportsCount": 0,
        "enableEnhancedTrivialQuery": "true",
    }

    # Two queries: India-biased catches mid/small caps, default catches large
    # caps that Yahoo prefers to surface via their US ADR (INFY, HDB, IBN, …).
    raw_quotes = _yh({**base, "region": "IN", "lang": "en-IN"}) + _yh(base)

    # Pass 1: pull every NSE-listed (.NS) result.
    by_symbol = {}  # bare symbol -> {symbol, yf_symbol, name, exchange}
    for item in raw_quotes:
        if item.get("quoteType") != "EQUITY":
            continue
        sym = item.get("symbol") or ""
        exch = item.get("exchange") or ""
        name = (item.get("shortname") or item.get("longname") or sym).strip()
        if sym.endswith(".NS") or exch == "NSI":
            bare = sym.replace(".NS", "")
            by_symbol[bare] = {
                "symbol": bare, "yf_symbol": f"{bare}.NS",
                "name": name, "exchange": "NSE",
            }

    # Pass 2: include BSE-listed entries — promoting big-cap dually-listed names
    # to the NSE form (most major Indian companies are listed on both).
    for item in raw_quotes:
        if item.get("quoteType") != "EQUITY":
            continue
        sym = item.get("symbol") or ""
        exch = item.get("exchange") or ""
        name = (item.get("shortname") or item.get("longname") or sym).strip()
        if not (sym.endswith(".BO") or exch == "BSE"):
            continue
        bare = sym.replace(".BO", "")
        if bare in by_symbol:
            continue  # already have NSE form
        # Filter out junk (mutual funds with numeric symbols slipping through,
        # weird sub-listings) by requiring a sane ticker shape.
        if not re.match(r"^[A-Z0-9&\-]{1,20}$", bare):
            continue
        by_symbol[bare] = {
            "symbol": bare, "yf_symbol": f"{bare}.NS",
            "name": name, "exchange": "NSE",
        }

    q_upper = q.upper()

    def _rank(hit):
        s = hit["symbol"].upper()
        n = hit["name"].upper()
        if s == q_upper:
            return (0, len(s))
        if s.startswith(q_upper):
            return (1, len(s))
        if n.startswith(q_upper):
            return (2, len(s))
        if q_upper in s:
            return (3, len(s))
        return (4, len(s))

    hits = sorted(by_symbol.values(), key=_rank)
    result = hits[:limit]
    _search_cache.set(cache_key, result)
    return result
