"""
Symbol normalisation.

A user can type:
  RELIANCE
  reliance
  NSE:RELIANCE
  RELIANCE.NS
  Tata Motors          (free-form name → resolved via Yahoo search)

We always normalise to the yfinance form (``RELIANCE.NS``) for downstream
use, while also remembering the bare NSE symbol (``RELIANCE``) for use
against screener.in.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from .cache import TTLCache

_search_cache = TTLCache(ttl_seconds=3600, max_entries=2048)


@dataclass
class Symbol:
    raw: str  # what the user typed
    nse: str  # bare NSE symbol e.g. "RELIANCE"
    yf: str   # yfinance form e.g. "RELIANCE.NS"


_VALID_NSE_TICKER = re.compile(r"^[A-Z0-9&\-]{1,20}$")


def normalize_symbol(user_input: str) -> Optional[Symbol]:
    """Normalise a free-form user string into a Symbol.

    1. Strip common prefixes/suffixes (NSE:, .NS, .BO, spaces).
    2. Upper-case.
    3. If the result matches an NSE-shaped ticker, accept it.
    4. Otherwise, fall back to Yahoo Finance search.
    """
    if not user_input:
        return None
    raw = user_input.strip()
    if not raw:
        return None

    cleaned = raw.upper()
    cleaned = re.sub(r"^(NSE|BSE):", "", cleaned)
    cleaned = re.sub(r"\.(NS|BO)$", "", cleaned)
    cleaned = cleaned.strip()

    if _VALID_NSE_TICKER.match(cleaned):
        return Symbol(raw=raw, nse=cleaned, yf=f"{cleaned}.NS")

    # Free-form name. Cache + Yahoo search fallback.
    cached = _search_cache.get(cleaned)
    if cached:
        return Symbol(raw=raw, nse=cached, yf=f"{cached}.NS")

    # Lazy import to avoid a cycle (nse imports nothing from us).
    from .nse import search_stocks

    hits = search_stocks(raw, limit=1)
    if not hits:
        return None
    sym_nse = hits[0]["symbol"]
    _search_cache.set(cleaned, sym_nse)
    return Symbol(raw=raw, nse=sym_nse, yf=f"{sym_nse}.NS")
