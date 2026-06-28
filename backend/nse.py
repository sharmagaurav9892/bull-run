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
from typing import Any, Dict, List, Optional

import requests
from curl_cffi import requests as crequests

from .cache import TTLCache

_company_cache = TTLCache(ttl_seconds=6 * 3600)
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
# Screener.in (the canonical source for Indian fundamentals)
#
# One fetch of the company page powers everything we surface from screener:
# headline ratios (P/E, ROCE, ROE, market cap — so our numbers MATCH the site
# users cross-check against), the auto-generated Pros & Cons, the "About"
# blurb, the official website + industry links, and the full shareholding
# history (so we can show the change vs the previous quarter).
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


def _strip_tags(html: str) -> str:
    """Plain text from an HTML fragment, dropping screener's [1]-style refs."""
    html = re.sub(r"<sup>.*?</sup>", "", html, flags=re.S)
    text = re.sub(r"<[^>]+>", "", html)
    return (
        text.replace("&nbsp;", " ")
        .replace("&amp;", "&")
        .replace("&#39;", "'")
        .replace("&quot;", '"')
        .strip()
    )


def _to_float(s: Optional[str]) -> Optional[float]:
    if s is None:
        return None
    s = s.replace(",", "").replace("%", "").replace("₹", "").strip()
    try:
        return float(s)
    except ValueError:
        return None


def _parse_ratios(html: str) -> Dict[str, Optional[float]]:
    """The top-of-page ratio strip: name -> numeric value."""
    out: Dict[str, Optional[float]] = {}
    block = re.search(r'<ul id="top-ratios".*?</ul>', html, re.S)
    if not block:
        return out
    for li in re.findall(r"<li[^>]*>(.*?)</li>", block.group(0), re.S):
        name = re.search(r'class="name">(.*?)</span>', li, re.S)
        num = re.search(r'class="number">(.*?)</span>', li, re.S)
        if name and num:
            out[_strip_tags(name.group(1))] = _to_float(_strip_tags(num.group(1)))
    return out


def _parse_list(html: str, css_class: str) -> List[str]:
    """Pros or Cons bullet list."""
    block = re.search(r'class="%s".*?<ul>(.*?)</ul>' % css_class, html, re.S)
    if not block:
        return []
    items = re.findall(r"<li[^>]*>(.*?)</li>", block.group(1), re.S)
    return [t for t in (_strip_tags(li) for li in items) if t]


def _parse_about(html: str) -> Optional[str]:
    m = re.search(r'class="sub show-more-box about"[^>]*>(.*?)</div>', html, re.S)
    if not m:
        return None
    about = _strip_tags(m.group(1))
    return about or None


def _parse_website(html: str) -> Optional[str]:
    # The first link in the company-links block carries the bare website icon
    # (icon-link), as opposed to the external BSE/NSE links (icon-link-ext).
    m = re.search(
        r'class="company-links.*?<a href="([^"]+)"[^>]*>\s*<i class="icon-link">',
        html,
        re.S,
    )
    return m.group(1) if m else None


def _parse_industry(html: str) -> Optional[Dict[str, str]]:
    """Most-specific classification from the sector→industry breadcrumb."""
    crumbs = re.findall(
        r'<a href="(/market/[^"]*)"[^>]*title="([^"]*)"[^>]*>(.*?)</a>', html, re.S
    )
    if not crumbs:
        return None
    chosen = None
    for href, title, text in crumbs:
        if title == "Industry":
            chosen = (href, text)
    if chosen is None:
        href, _title, text = crumbs[-1]
        chosen = (href, text)
    return {"name": _strip_tags(chosen[1]), "url": "https://www.screener.in" + chosen[0]}


_SH_LABELS = {
    "promoter": ("promoter",),
    "fii": ("fii",),
    "dii": ("dii",),
    "government": ("government",),
    "public": ("public",),
}


def _parse_shareholding(html: str) -> Optional[Dict[str, Any]]:
    """Latest + previous quarter holdings (so we can show the change)."""
    anchor = html.find('id="shareholding"')
    if anchor < 0:
        return None
    section = html[anchor:]
    table = re.search(r"<table[^>]*>.*?</table>", section, re.S)
    if not table:
        return None
    tbl = table.group(0)

    head = re.search(r"<thead.*?</thead>", tbl, re.S)
    quarters = (
        [_strip_tags(t) for t in re.findall(r"<th[^>]*>(.*?)</th>", head.group(0), re.S)]
        if head
        else []
    )
    body = re.search(r"<tbody.*?</tbody>", tbl, re.S)
    if not body:
        return None

    rowmap: Dict[str, List[Optional[float]]] = {}
    for row in re.findall(r"<tr[^>]*>(.*?)</tr>", body.group(0), re.S):
        label = re.search(r"<button[^>]*>(.*?)</span>", row, re.S) or re.search(
            r'<td class="text">(.*?)</td>', row, re.S
        )
        if not label:
            continue
        key = _strip_tags(label.group(1)).rstrip("+").strip().lower()
        cells = re.findall(r"<td[^>]*>(.*?)</td>", row, re.S)[1:]  # drop label cell
        rowmap[key] = [_to_float(_strip_tags(c)) for c in cells]

    def pick(*names) -> Optional[List[Optional[float]]]:
        for n in names:
            for k, vals in rowmap.items():
                if k.startswith(n):
                    return vals
        return None

    def at(vals: Optional[List[Optional[float]]], back: int) -> Optional[float]:
        if not vals or len(vals) < back + 1:
            return None
        return vals[-(back + 1)]

    latest: Dict[str, Optional[float]] = {}
    changes: Dict[str, Optional[float]] = {}
    found_any = False
    for key, names in _SH_LABELS.items():
        vals = pick(*names)
        cur = at(vals, 0)
        prev = at(vals, 1)
        latest[key] = cur
        if cur is not None and prev is not None:
            changes[key] = round(cur - prev, 2)
        else:
            changes[key] = None
        if cur is not None:
            found_any = True

    if not found_any:
        return None

    return {
        "period": quarters[-1] if quarters else "",
        "prev_period": quarters[-2] if len(quarters) > 1 else "",
        "promoter": latest.get("promoter"),
        "fii": latest.get("fii"),
        "dii": latest.get("dii"),
        "public": latest.get("public"),
        "government": latest.get("government"),
        "changes": changes,
    }


def get_company_data(symbol_nse: str) -> Dict[str, Any]:
    """Everything we scrape from screener.in in a single page fetch.

    Returns a dict (never None) with keys: ratios, pros, cons, about, website,
    industry, shareholding. Missing pieces are None / empty so callers can rely
    on the shape. Cached so a lookup + its compare reuse one fetch.
    """
    cached = _company_cache.get(symbol_nse)
    if cached is not None:
        return cached

    empty: Dict[str, Any] = {
        "ratios": {},
        "pros": [],
        "cons": [],
        "about": None,
        "website": None,
        "industry": None,
        "shareholding": None,
    }

    sess = _screener()
    html = None
    # Consolidated first (most relevant for groups), then standalone.
    for url in (
        f"https://www.screener.in/company/{symbol_nse}/consolidated/",
        f"https://www.screener.in/company/{symbol_nse}/",
    ):
        try:
            r = sess.get(url, timeout=12)
        except Exception:
            continue
        if r.status_code == 200 and "top-ratios" in r.text:
            html = r.text
            break

    if html is None:
        # Cache the miss briefly so a dead symbol doesn't hammer screener.
        _company_cache.set(symbol_nse, empty)
        return empty

    data = {
        "ratios": _parse_ratios(html),
        "pros": _parse_list(html, "pros"),
        "cons": _parse_list(html, "cons"),
        "about": _parse_about(html),
        "website": _parse_website(html),
        "industry": _parse_industry(html),
        "shareholding": _parse_shareholding(html),
    }
    _company_cache.set(symbol_nse, data)
    return data


def get_shareholding(symbol_nse: str) -> Optional[Dict[str, Any]]:
    """Latest shareholding pattern (with quarter-over-quarter change)."""
    return get_company_data(symbol_nse).get("shareholding")


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
