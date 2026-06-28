# 🐂 Bull Run — How We Put It On The Internet (Explained Simply)

> A complete, beginner-friendly write-up of everything we did today to take the
> Bull Run app from "runs on my laptop" to "live at
> **https://bullrun.gauravsharma.xyz**". Written for an engineering student.
> Copy this whole file into your Notes app for future reference.

---

## 1. The 30-Second Summary

We took an app that only ran on your Mac and made it available to the whole
world at a nice web address. To do that, four different services each did one
job:

```
   YOUR CODE            THE SERVER           THE ADDRESS          THE DISGUISE
  ┌──────────┐         ┌──────────┐         ┌──────────┐         ┌──────────┐
  │  GitHub  │ ──────> │  Render  │ <────── │Cloudflare│         │ Webshare │
  │ (storage)│  pulls  │ (runs it)│  points │  (DNS)   │         │ (proxy)  │
  └──────────┘  code   └──────────┘   to    └──────────┘         └────┬─────┘
                                                                       │
                                            Render uses Webshare ──────┘
                                            to fetch stock data
```

| Service        | One-line job                                              |
|----------------|-----------------------------------------------------------|
| **GitHub**     | Stores your code (the filing cabinet)                     |
| **Render.com** | Runs your Python app on a real server 24/7 (the kitchen)  |
| **Cloudflare** | Connects your domain name to that server (the signpost)   |
| **Webshare.io**| A "disguise" so the server can fetch stock data (the mask)|

---

## 2. First, What IS This App?

Bull Run is **not** just a web page. It's a **program that runs and does work**:

- A **frontend** — the HTML/CSS/JavaScript you see in the browser (the buttons,
  charts, the search box).
- A **backend** — a Python program (using a framework called **FastAPI**) that,
  every time you search a stock, goes and **fetches live data** from the
  internet (Yahoo Finance, screener.in), does calculations (P/E, ROE,
  Piotroski score…), and sends the answer back.

This distinction is the KEY to understanding everything below 👇

```
  STATIC website                    DYNAMIC website (ours)
  ┌─────────────────┐               ┌─────────────────────────────┐
  │ Just files.     │               │ Files  +  a running program │
  │ HTML, CSS, JS,  │               │ that thinks, calculates,    │
  │ images.         │               │ and fetches fresh data.     │
  │                 │               │                             │
  │ Like a printed  │               │ Like a waiter who runs to   │
  │ poster on a     │               │ the kitchen and brings you  │
  │ wall.           │               │ a freshly cooked dish.      │
  └─────────────────┘               └─────────────────────────────┘
```

---

## 3. Why NOT Just Use Cloudflare Directly?

You bought your domain on Cloudflare, so the natural question is:
*"Can't Cloudflare just host the whole thing?"*

Cloudflare has a product called **Cloudflare Pages**. But Pages can only host
**STATIC** websites — plain files. It **cannot run a Python program**.

```
  Can Cloudflare Pages run our Python backend?

  Our app needs:  [ Run Python ] [ Call Yahoo live ] [ Do math per request ]
  Cloudflare Pages:    ❌               ❌                    ❌
  → It only serves pre-made files. No "kitchen", just a "poster wall".
```

**Analogy:** Cloudflare Pages is a **billboard company** — brilliant at sticking
up a poster for millions to see. But you asked for a **restaurant with a live
kitchen**. A billboard can't cook. So we needed a real server elsewhere.

> 💡 Cloudflare *does* have ways to run code (Workers), but they don't run normal
> Python apps like ours, so it's the wrong tool here.

That's why we split the job: **Render runs the app**, and **Cloudflare just
points your domain at it**.

---

## 4. Step A — GitHub: Where The Code Lives

You had already pushed your code to:
`https://github.com/sharmagaurav9892/bull-run`

GitHub is like a **cloud filing cabinet** for code. Important for us because:

```
  You ──push──> GitHub ──Render watches──> auto-deploys new version
```

Every time you `git push`, Render notices and **automatically rebuilds and
re-deploys** the app. This is called **auto-deploy / continuous deployment**.
You change code on your laptop → push → the live site updates itself. Magic. ✨

---

## 5. Step B — Render.com: The Server That Runs Your App

**Render** is a hosting company that takes your code and runs it on a real
computer in a data center, online 24/7.

### How Render knew what to do
Your repo already had a file called `render.yaml` — a **recipe** that tells
Render exactly how to start the app:

```yaml
buildCommand: pip install -r requirements.txt          # install ingredients
startCommand: uvicorn backend.main:app --host 0.0.0.0  # start cooking
healthCheckPath: /api/health                           # "are you alive?" check
```

### What happened, visually
```
   GitHub repo ─┐
                │  1. Render pulls the code
                ▼
        ┌───────────────┐
        │   RENDER       │  2. Runs: pip install -r requirements.txt
        │   (the server) │  3. Runs: uvicorn backend.main:app
        │                │  4. App is now live at:
        └───────────────┘     https://bull-run.onrender.com
```

### The first hiccup we hit: "Not Found"
When you first opened `bull-run.onrender.com` it said **"Not Found"**. That was
just a **cold start** — Render's free plan puts the app to **sleep after ~15 min
of no visitors** to save resources. The first visit "wakes it up" and can take
~30–50 seconds, and mid-wake it briefly errors. A refresh fixed it.

```
  Free plan behavior:
  No visitors for 15 min ──> 😴 app sleeps
  Someone visits         ──> ⏰ wakes up (~30-50s) ──> 😀 serves page
```

> 💡 To avoid the sleep: pay ~$7/month for an always-on plan, OR set up a free
> "pinger" (like UptimeRobot) that visits every 10 min to keep it awake.

---

## 6. Step C — Cloudflare: Pointing Your Domain At Render

Render gave us an ugly default address: `bull-run.onrender.com`.
You wanted your own: `bullrun.gauravsharma.xyz`.

This is a job for **DNS** (Domain Name System) — the internet's **phone book**.
It translates human names into machine addresses.

```
  You type:   bullrun.gauravsharma.xyz
                        │
                        ▼
              ┌──────────────────┐
              │   DNS lookup     │   "What does this name point to?"
              │  (Cloudflare)    │
              └────────┬─────────┘
                        │  "It points to bull-run.onrender.com"
                        ▼
              ┌──────────────────┐
              │   Render server  │   serves the Bull Run app
              └──────────────────┘
```

### What we actually did in Cloudflare
We added one **CNAME record**. A CNAME is just a rule that says
*"this name is an alias for that name."*

```
  TYPE    NAME      TARGET                   MEANING
  CNAME   bullrun   bull-run.onrender.com    "bullrun.gauravsharma.xyz
                                              is an alias for the Render app"
```

And in Render, we added `bullrun.gauravsharma.xyz` as a **Custom Domain** so it
knows to accept visitors arriving under that name (and to give it an HTTPS
🔒 security certificate, for free).

**Analogy:** Render is a house. `bull-run.onrender.com` is its long GPS
coordinate. Cloudflare DNS is the **street signpost** that says
"Bull Run → this way," so people can find it by a friendly name.

---

## 7. Step D — The Big Bug: Why We Needed A Proxy 🕵️

This is the most interesting part. After deploying, the app loaded, charts
worked, search worked… but **"Lookup & Compare" failed** with:

```
   Could not resolve symbol 'ICICIBANK' on NSE
```

### How we debugged it (the detective work)
We tested the same app in two places and compared:

```
  TEST                          On your Mac      On Render server
  ───────────────────────────   ───────────      ────────────────
  Search a stock                   ✅ works          ✅ works
  Price chart                      ✅ works          ✅ works
  Fundamentals (P/E, ROE...)       ✅ works          ❌ FAILS
```

Same code, same stock (even giant stocks like RELIANCE failed on Render). So it
was **NOT a bug in your code**. The difference was *where the request came from*.

### The root cause
Yahoo Finance (where the app gets fundamentals) has **different doors**:

```
  Yahoo Finance's data doors:

  ┌─ "search" door ─────────┐   open to everyone        ✅
  ┌─ "chart" door ──────────┐   open to everyone        ✅
  ┌─ "quoteSummary" door ───┐   needs a secret pass     🔒
     (P/E, ROE, financials)     AND blocks data-center
                                IP addresses
```

The fundamentals come through Yahoo's **`quoteSummary`** door, which needs a
special token (a "crumb") AND **refuses requests coming from data-center
computers** like Render's servers. Yahoo does this to stop bots/scrapers.

Your home internet has a **residential IP** (a normal household address), so
Yahoo trusts it. Render's server has a **data-center IP** (an obvious
"this is a robot" address), so Yahoo slams that door.

```
  Your Mac (home IP)  ──"hello, I'm a normal person"──>  Yahoo  ✅ "come in"
  Render (server IP)  ──"hello, I'm a data center"────>  Yahoo  ❌ "blocked"
```

### What a PROXY is, and how it fixed it
A **proxy** is a middle-man server that forwards your request and makes it look
like it came from *somewhere else*. We used **Webshare.io**, which rents out
**residential proxies** — middle-men with normal household IP addresses.

```
  WITHOUT proxy (blocked):
  Render ───────────────────────────────────> Yahoo
         "I'm a data center"                    ❌ blocked

  WITH Webshare proxy (works):
  Render ──> Webshare proxy ──────────────────> Yahoo
            (a home-looking IP)  "I'm a normal person"  ✅ allowed
                                                    │
                                  data flows back ◄─┘
```

**Analogy:** A bouncer (Yahoo) won't let a delivery robot (Render) into the
club. So the robot hands its request to a **regular-looking person (the
Webshare proxy)** who walks in, gets the info, and hands it back. Same goal,
acceptable disguise.

### What we changed in the code
We edited `backend/fundamentals.py` to do two things:

1. **Pretend to be a real Chrome browser** (using a library called `curl_cffi`)
   so the request looks human, not bot-like.
2. **Optionally route through a proxy** if a `YF_PROXY` setting is present.

Then on Render, we added an environment variable:

```
  KEY:   YF_PROXY
  VALUE: http://username:password@proxy-host:port   (from Webshare)
```

The code reads that variable and sends all Yahoo requests through the proxy.
Result: **fundamentals now work in production.** 🎉

> 💡 **Environment variable** = a setting you give the app from *outside* the
> code (like a sticky note on the server). Great for secrets like proxy
> passwords, because you don't want them written inside your public GitHub code.

---

## 8. The Final Architecture (All Together)

```
                                 ┌──────────────┐
   You push code  ──────────────>│    GitHub    │  stores the code
                                 └──────┬───────┘
                                        │ auto-deploy on push
                                        ▼
   bullrun.gauravsharma.xyz      ┌──────────────┐
            │                    │  RENDER.com  │  runs the Python app 24/7
            │ DNS lookup         │  (FastAPI)   │
            ▼                    └──────┬───────┘
     ┌────────────┐                    │ needs stock data
     │ CLOUDFLARE │ ──points name──────┘ │
     │   (DNS)    │   to Render          │ via proxy (disguise)
     └────────────┘                      ▼
                                  ┌──────────────┐      ┌──────────────┐
                                  │  WEBSHARE    │─────>│ Yahoo Finance│
                                  │  (proxy)     │      │ screener.in  │
                                  └──────────────┘      └──────────────┘

   A visitor's journey:
   Browser → Cloudflare (find the address) → Render (run app)
           → Webshare (fetch data safely) → Yahoo → back to your screen
```

---

## 9. Cheat-Sheet: What Each Service Does & Its Features

### 🟦 Cloudflare — *the domain & DNS company*
- **Bought your domain** (`gauravsharma.xyz`) here.
- **DNS**: the phone book that points your name to the Render server (the CNAME).
- **Free HTTPS / SSL** (the 🔒 padlock) — encrypts traffic.
- **CDN & caching**: can serve content faster from servers near each visitor.
- **DDoS protection & firewall**: blocks attacks and bad traffic.
- ❗ **Cannot run our Python app** — only static files (Cloudflare Pages).

### 🟩 Render.com — *the app hosting company*
- **Runs your actual program** (Python/FastAPI) on a real server, 24/7.
- **Auto-deploy from GitHub**: push code → it rebuilds & redeploys automatically.
- **Reads `render.yaml`** to know how to build and start the app.
- **Free HTTPS** and easy **custom domain** support.
- **Environment variables** for secrets (we used `YF_PROXY` here).
- **Health checks** (`/api/health`) to confirm the app is alive.
- ❗ **Free plan sleeps** after ~15 min idle (slow first wake-up).

### 🟨 Webshare.io — *the proxy company*
- Rents **proxy servers** that forward your requests.
- **Residential/rotating IPs** that look like normal home users.
- Lets a blocked data-center app (Render) **reach sites that block servers**
  (Yahoo Finance, in our case).
- **Free tier**: ~10 proxies, ~1 GB/month — enough for a personal project.
- ❗ Adds a small extra step/latency; only needed because Yahoo blocks servers.

### ⬛ GitHub — *the code storage*
- Stores all your code, with full history (version control).
- The **single source of truth** Render pulls from.
- Push triggers the whole deploy pipeline.

---

## 10. Mini Glossary (Plain English)

| Term | Plain meaning |
|------|---------------|
| **Frontend** | What you see in the browser (buttons, charts). |
| **Backend** | The program on the server that does the work. |
| **Static site** | Just files; no live program. (Cloudflare Pages can host.) |
| **Dynamic site** | Files + a running program. (Needs Render.) |
| **Deploy** | Putting your code onto a live server. |
| **DNS** | The internet's phone book (name → server address). |
| **CNAME** | A DNS rule: "this name is an alias for that name." |
| **Custom domain** | Using your own name instead of `*.onrender.com`. |
| **Cold start** | Slow first load because the app was asleep. |
| **IP address** | A computer's address on the internet. |
| **Residential IP** | A home internet address (trusted). |
| **Data-center IP** | A server address (often blocked as "bot"). |
| **Proxy** | A middle-man that forwards your request in disguise. |
| **Environment variable** | A setting given to the app from outside the code. |
| **HTTPS / SSL** | The 🔒 that encrypts traffic between browser and server. |
| **Auto-deploy** | Push code → site updates itself automatically. |
| **API** | A "door" a program uses to ask another service for data. |

---

## 11. Recap Checklist — Everything We Did Today

1. ✅ Confirmed Bull Run is a **dynamic app** (needs to run Python), so plain
   Cloudflare hosting won't work.
2. ✅ Code was already on **GitHub**.
3. ✅ Deployed to **Render.com** using the `render.yaml` recipe → got
   `bull-run.onrender.com`.
4. ✅ Fixed the "Not Found" — it was just a **cold start**; refresh solved it.
5. ✅ Added a **CNAME in Cloudflare** (`bullrun` → `bull-run.onrender.com`) and
   a **custom domain in Render** → site live at `bullrun.gauravsharma.xyz`.
6. ✅ Debugged "Could not resolve symbol": found Yahoo **blocks data-center IPs**
   on its fundamentals API (code was fine — proved by local vs. server test).
7. ✅ Updated `backend/fundamentals.py` to impersonate Chrome + support a proxy.
8. ✅ Signed up for **Webshare.io**, added the `YF_PROXY` environment variable on
   Render → **fundamentals now work in production.** 🎉

---

## 12. If Something Breaks Later — Quick Fixes

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| Site slow on first open | Free plan cold start | Wait ~40s / refresh, or upgrade plan |
| "Could not resolve symbol" again | Proxy ran out of data / expired | Check Webshare usage; update `YF_PROXY` |
| Site totally down | Bad deploy | Check Render **Logs** tab for the error |
| Domain not loading | DNS issue | Recheck the Cloudflare CNAME record |
| Changes not showing | Forgot to push | `git push origin main`, Render redeploys |

---

*Made on 2026-06-28. Keep this for reference — it explains the "why" behind
every piece, not just the "how".* 🐂📈
