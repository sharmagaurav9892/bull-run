# Bull Run

A clean, dark-themed web app for **NSE-listed stocks** built in the same
visual language as the Snake game next door. Three things:

1. **Lookup** — type any NSE ticker (`RELIANCE`, `NSE:TCS`, `INFY.NS`, …)
   and get the core fundamentals + a price-returns chart.
2. **Compare** — pit 2–4 NSE tickers against each other across the same
   fundamentals and get a winner-per-metric + an overall verdict.
3. **OHLC Export** — upload a CSV of NSE tickers and download a single
   combined CSV of daily OHLC for 1M / 1Y / 5Y / 10Y / 20Y.

```
bull-run/
├── backend/
│   ├── main.py          FastAPI app + routes + static mount
│   ├── symbols.py       NSE symbol resolution + shared HTTP session
│   ├── nse.py           Sectoral index P/E + shareholding pattern
│   ├── fundamentals.py  yfinance wrapper + Piotroski + Altman Z
│   ├── prices.py        Price series for the chart
│   ├── compare.py       Per-metric winner + overall verdict
│   ├── ohlc.py          CSV upload → combined OHLC CSV
│   └── cache.py         Tiny TTL cache
├── static/
│   ├── index.html       Markup (3 tabs)
│   ├── styles.css       Emerald-on-charcoal theme (same tokens as Snake)
│   ├── app.js           Frontend logic (vanilla + Chart.js CDN)
│   └── favicon.svg
├── requirements.txt     Python deps
├── Procfile             For Heroku-style platforms
├── render.yaml          One-click Render blueprint
├── runtime.txt          Python 3.11.9
└── README.md
```

## Data sources

| Field                             | Source                                    |
| --------------------------------- | ----------------------------------------- |
| Current Price, Market Cap         | `yfinance` (Yahoo Finance, `.NS` ticker)  |
| Stock P/E, Forward P/E, PEG       | `yfinance`                                |
| ROE, Debt/Equity                  | `yfinance`                                |
| ROCE                              | Computed from balance sheet + EBIT        |
| **Piotroski F-score** (0–9)       | Computed from 2 annual statements         |
| **Altman Z-score**                | Computed from balance sheet + market cap  |
| Sectoral P/E                      | NSE `allIndices` API, mapped from sector  |
| 1D / 1W / 1M / 1Y / 5Y returns    | Computed from yfinance daily history      |
| Shareholding (Promoter/FII/DII/Public) | NSE `quote-equity?section=corp_info`  |
| OHLC                              | `yfinance` daily candles                  |

Any source that's down or missing degrades to **N/A** — the UI never breaks.

## Run locally

```bash
cd bull-run
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Important: only watch our source dirs, NOT .venv.
# (Otherwise uvicorn restarts every time macOS touches a file
#  inside .venv/lib/.../tzdata/... and you get a reload loop.)
uvicorn backend.main:app \
  --reload \
  --reload-dir backend \
  --reload-dir static \
  --port 8000

# open http://localhost:8000
```

That's the entire dev loop — there's no build step.

If you don't need auto-reload, the simplest invocation is:

```bash
uvicorn backend.main:app --port 8000
```

### About the `urllib3 / LibreSSL` warning

If you're on macOS using the system Python (3.9 ships with LibreSSL),
`urllib3` prints a `NotOpenSSLWarning` once per process. It's cosmetic —
every request still works. The app suppresses it at startup, but if you
import `requests`/`yfinance` from a Python REPL outside the app you'll
still see it. To get rid of it entirely, install a newer Python:

```bash
brew install python@3.11
python3.11 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

## API (if you want to script it)

| Method | Path                              | What                                 |
| ------ | --------------------------------- | ------------------------------------ |
| GET    | `/api/health`                     | Liveness probe                       |
| GET    | `/api/stock/{symbol}`             | Fundamentals + returns               |
| GET    | `/api/stock/{symbol}/chart?range=1d\|1w\|1m\|1y\|5y` | Price series       |
| POST   | `/api/compare` `{symbols:[…]}`    | 2–4 stock comparison + verdict       |
| POST   | `/api/ohlc/csv` (multipart)       | Upload CSV, returns OHLC CSV         |

---

## Deploying to `bullrun.gauravsharma.xyz`

Because Bull Run has a Python backend, GitHub Pages alone isn't enough.
The pattern that gives you a custom Cloudflare subdomain *and* keeps you on
a free tier is:

> **GitHub (source) → Render (runs the backend) → Cloudflare DNS (CNAME)**.

You only do this once.

### 1. Push the repo to GitHub

```bash
cd bull-run
git init
git add .
git commit -m "Bull Run: NSE fundamentals, comparisons, OHLC export"
git branch -M main
git remote add origin git@github.com:<your-username>/bull-run.git
git push -u origin main
```

### 2. Deploy on Render (free tier, no credit card)

1. Go to <https://render.com>, sign in with GitHub.
2. **New +** → **Blueprint** → pick the `bull-run` repo. Render reads
   [`render.yaml`](./render.yaml) and creates the service automatically.
   (If you prefer the manual route: **New + → Web Service**, runtime
   *Python*, build `pip install -r requirements.txt`, start
   `uvicorn backend.main:app --host 0.0.0.0 --port $PORT`.)
3. Wait ~3–4 minutes for the first build. You'll get a URL like
   `https://bull-run.onrender.com`.
4. Open it — the app should load. Try `RELIANCE` in Lookup.

> **Heads-up on the free plan:** the service sleeps after 15 min of
> inactivity. First request after a sleep takes ~30 s to wake. If that's
> annoying, upgrade to the $7/mo Starter plan or switch to
> [Fly.io](https://fly.io) (also has a generous free tier).

### 3. Point `bullrun.gauravsharma.xyz` at Render

#### a) Tell Render about the custom domain

- In your Render service → **Settings** → **Custom Domains** →
  **Add Custom Domain** → enter `bullrun.gauravsharma.xyz` → **Save**.
- Render shows you a target hostname, something like
  `bull-run.onrender.com` (or a longer `cname.render.com` form). Copy it.

#### b) Add the CNAME in Cloudflare

1. Cloudflare dashboard → pick `gauravsharma.xyz` → **DNS** → **Records**
   → **Add record**.
2. Fill it in:
   - **Type:** `CNAME`
   - **Name:** `bullrun`
   - **Target:** the hostname Render gave you (e.g. `bull-run.onrender.com`)
   - **Proxy status:** **DNS only** (grey cloud) for the first 10 minutes
     so Render's ACME challenge can issue the SSL cert.
   - **TTL:** Auto
3. Save.

#### c) Wait for the cert, then flip the proxy on

- Back in Render → **Custom Domains** → wait until the entry goes
  **Verified** with a green checkmark (usually 1–10 minutes).
- Visit `https://bullrun.gauravsharma.xyz` — it should serve Bull Run.
- Then in Cloudflare → DNS, click the grey cloud on the `bullrun` record
  to turn it **orange** (proxied). You now get Cloudflare's CDN, DDoS
  protection, and edge SSL on top of Render's origin.

> Cloudflare SSL/TLS mode for the zone should be **Full** or
> **Full (strict)** — *not* Flexible, because Render only listens on HTTPS.

### 4. After every code change

```bash
git add .
git commit -m "your message"
git push
```

Render is watching `main`. It rebuilds and deploys automatically — no
manual step. Cloudflare and the custom domain keep working as-is.

---

## Notes and limitations

- **NSE endpoints can rate-limit cloud IPs.** Shareholding and sectoral
  P/E are best-effort and silently fall back to N/A when NSE blocks the
  request. The rest of the fundamentals come from Yahoo Finance, which
  is much more reliable from cloud hosts.
- **Piotroski and Altman Z need 2 years of statements.** Newly listed
  companies will show N/A for these until enough history is available.
- **CSV upload is capped at 200 tickers per request** to keep response
  times reasonable on the free tier. Split bigger lists into multiple
  uploads.
- **All data is cached for 10–15 minutes** in memory to be a good
  citizen with upstream APIs. Restarts clear the cache.
