"""
Bull Run backend
=================
FastAPI service that powers the Bull Run UI:

  GET  /api/health
  GET  /api/stock/{symbol}              -> fundamentals + returns
  GET  /api/stock/{symbol}/chart?range= -> price series for the chart
  POST /api/compare                     -> compare 2..4 tickers
  POST /api/ohlc/csv                    -> upload CSV/TXT of tickers, download OHLC CSV

The frontend is served as static files from ../static.
"""

from __future__ import annotations

import io
import os
import warnings
from pathlib import Path
from typing import List, Optional

# macOS system Python 3.9 ships with LibreSSL, which urllib3 v2 grumbles about
# on every import. Silence the warning before the first request kicks it off.
warnings.filterwarnings("ignore", message=r"urllib3 v2 only supports OpenSSL.*")
try:  # urllib3 may or may not be importable at this point depending on env
    import urllib3
    urllib3.disable_warnings()
except Exception:
    pass

import hashlib

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .compare import build_comparison
from .fundamentals import get_fundamentals
from .nse import search_stocks
from .ohlc import build_ohlc_csv, parse_tickers
from .prices import get_return_series

ROOT_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = ROOT_DIR / "static"

app = FastAPI(
    title="Bull Run API",
    description="Fundamentals, comparisons, and OHLC export for NSE-listed stocks.",
    version="1.0.0",
)

# Permissive CORS so the same backend can serve the SPA and also be hit from
# bullrun.gauravsharma.xyz once deployed behind Cloudflare.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class CompareRequest(BaseModel):
    symbols: List[str] = Field(..., min_length=2, max_length=4)


# ---------------------------------------------------------------------------
# API routes
# ---------------------------------------------------------------------------


@app.get("/api/health")
def health():
    return {"ok": True, "service": "bull-run"}


@app.get("/api/search")
def search(q: str = "", limit: int = 8):
    q = (q or "").strip()
    if not q:
        return {"results": []}
    if limit < 1 or limit > 15:
        limit = 8
    return {"results": search_stocks(q, limit=limit)}


@app.get("/api/stock/{symbol}")
def stock(symbol: str):
    data = get_fundamentals(symbol)
    if data is None:
        raise HTTPException(status_code=404, detail=f"Could not resolve symbol '{symbol}' on NSE.")
    return data


@app.get("/api/stock/{symbol}/chart")
def stock_chart(symbol: str, range: str = "1y"):
    series = get_return_series(symbol, range)
    if series is None:
        raise HTTPException(status_code=404, detail=f"No price history for '{symbol}'.")
    return series


@app.post("/api/compare")
def compare(req: CompareRequest):
    result = build_comparison(req.symbols)
    return result


@app.post("/api/ohlc/csv")
async def ohlc_csv(
    file: UploadFile = File(...),
    range: str = Form("1y"),
):
    raw = await file.read()
    try:
        tickers = parse_tickers(raw)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    if not tickers:
        raise HTTPException(status_code=400, detail="No tickers found in the uploaded file.")

    csv_text, summary = build_ohlc_csv(tickers, range)
    buf = io.BytesIO(csv_text.encode("utf-8"))
    filename = f"bullrun_ohlc_{range}.csv"
    headers = {
        "Content-Disposition": f'attachment; filename="{filename}"',
        "X-Bullrun-Summary": summary,
    }
    return StreamingResponse(buf, media_type="text/csv", headers=headers)


# ---------------------------------------------------------------------------
# Static SPA
# ---------------------------------------------------------------------------


def _asset_version() -> str:
    """Short content hash of the CSS/JS so we can cache-bust them.

    The domain sits behind Cloudflare, which caches static assets aggressively.
    We stamp the asset URLs in index.html with ?v=<hash>; when their contents
    change, the URL changes, so a deploy is picked up immediately instead of
    serving a stale stylesheet/script from the edge cache.
    """
    h = hashlib.md5()
    for name in ("styles.css", "app.js", "favicon.svg"):
        try:
            h.update((STATIC_DIR / name).read_bytes())
        except OSError:
            pass
    return h.hexdigest()[:10]


_ASSET_V = _asset_version()


if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.get("/")
    def index():
        # Inject the asset version so cached CSS/JS bust on every content change.
        html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
        html = html.replace("__ASSET_V__", _ASSET_V)
        return HTMLResponse(html)

    @app.get("/favicon.ico")
    def favicon():
        path = STATIC_DIR / "favicon.svg"
        if path.exists():
            return FileResponse(path, media_type="image/svg+xml")
        return JSONResponse({"detail": "no favicon"}, status_code=404)


if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", "8000"))
    uvicorn.run("backend.main:app", host="0.0.0.0", port=port, reload=True)
