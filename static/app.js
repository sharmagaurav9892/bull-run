/* =====================================================================
 * Bull Run frontend
 * Same coding style as Snake: IIFE, no framework, no build step.
 * ===================================================================== */

(() => {
  "use strict";

  // -------------------- DOM ----------------------------
  const els = {
    tabs: document.querySelectorAll(".tab"),
    panels: {
      lookup: document.getElementById("panel-lookup"),
      compare: document.getElementById("panel-compare"),
      ohlc: document.getElementById("panel-ohlc"),
    },

    // Lookup
    lookupInput: document.getElementById("lookupInput"),
    lookupAc: document.getElementById("lookupAc"),
    lookupBtn: document.getElementById("lookupBtn"),
    lookupState: document.getElementById("lookupState"),
    lookupLoader: document.getElementById("lookupLoader"),
    lookupResult: document.getElementById("lookupResult"),
    lookupName: document.getElementById("lookupName"),
    lookupSymbol: document.getElementById("lookupSymbol"),
    lookupSector: document.getElementById("lookupSector"),
    lookupPrice: document.getElementById("lookupPrice"),
    groupValuation: document.getElementById("groupValuation"),
    groupProfit: document.getElementById("groupProfit"),
    groupHealth: document.getElementById("groupHealth"),
    groupReturns: document.getElementById("groupReturns"),
    lookupHolding: document.getElementById("lookupHolding"),
    holdingPeriod: document.getElementById("holdingPeriod"),
    aboutGroup: document.getElementById("aboutGroup"),
    aboutText: document.getElementById("aboutText"),
    aboutLinks: document.getElementById("aboutLinks"),
    aboutWebsite: document.getElementById("aboutWebsite"),
    proconGroup: document.getElementById("proconGroup"),
    prosList: document.getElementById("prosList"),
    consList: document.getElementById("consList"),
    newsGroup: document.getElementById("newsGroup"),
    newsList: document.getElementById("newsList"),
    rangeToggle: document.getElementById("rangeToggle"),
    chartCanvas: document.getElementById("lookupChart"),
    chartState: document.getElementById("chartState"),
    chartReturn: document.getElementById("chartReturn"),

    // Compare
    compareInputs: document.querySelectorAll("[data-cmp-idx]"),
    compareBtn: document.getElementById("compareBtn"),
    compareClearBtn: document.getElementById("compareClearBtn"),
    compareState: document.getElementById("compareState"),
    compareLoader: document.getElementById("compareLoader"),
    compareResult: document.getElementById("compareResult"),
    compareVerdict: document.getElementById("compareVerdict"),
    cmpTable: document.getElementById("cmpTable"),

    // OHLC
    fileBrowseBtn: document.getElementById("fileBrowseBtn"),
    fileInput: document.getElementById("ohlcFile"),
    fileName: document.getElementById("fileName"),
    fileDrop: document.getElementById("fileDrop"),
    ohlcRange: document.getElementById("ohlcRange"),
    ohlcBtn: document.getElementById("ohlcBtn"),
    ohlcState: document.getElementById("ohlcState"),
    ohlcLoader: document.getElementById("ohlcLoader"),

    toast: document.getElementById("toast"),
  };

  // -------------------- State --------------------------
  const state = {
    currentSymbol: null,   // last analysed symbol input (raw)
    currentRange: "1y",
    chart: null,
    ohlcRange: "1y",
    ohlcFile: null,
  };

  const API = ""; // same origin

  // -------------------- Helpers ------------------------
  function fmtNumber(v, opts = {}) {
    if (v === null || v === undefined || Number.isNaN(v)) return "—";
    const { digits = 2, suffix = "" } = opts;
    return Number(v).toLocaleString("en-IN", {
      minimumFractionDigits: digits,
      maximumFractionDigits: digits,
    }) + suffix;
  }
  function fmtPct(v, digits = 2) {
    if (v === null || v === undefined || Number.isNaN(v)) return "—";
    const sign = v > 0 ? "+" : "";
    return sign + Number(v).toFixed(digits) + "%";
  }
  function fmtCr(v) {
    if (v === null || v === undefined) return "—";
    if (v >= 1e5) return (v / 1e5).toFixed(2) + " L Cr";
    return Number(v).toLocaleString("en-IN", { maximumFractionDigits: 0 }) + " Cr";
  }
  function trendClass(v) {
    if (v === null || v === undefined) return "";
    return v >= 0 ? "stat__value--up" : "stat__value--down";
  }
  function show(el) { el.classList.remove("hidden"); }
  function hide(el) { el.classList.add("hidden"); }

  // -------------------- Animated loader ----------------
  // One delightful scene reused across Lookup / Compare / OHLC:
  // candlesticks build a rally, a trend line draws itself, a rocket
  // rides the leading edge, sparks fly, and a witty status line cycles.
  const TREND_PATH = "M26 120 C 92 112 132 92 168 72 C 214 46 252 36 282 24";
  const ROCKET_SVG = `
    <svg viewBox="0 0 64 100" xmlns="http://www.w3.org/2000/svg">
      <defs>
        <linearGradient id="rg-body" x1="0" x2="0" y1="0" y2="1">
          <stop offset="0" stop-color="#e6edf3"/><stop offset="1" stop-color="#8b95a5"/>
        </linearGradient>
        <linearGradient id="rg-flame" x1="0" x2="0" y1="0" y2="1">
          <stop offset="0" stop-color="#fff0c2"/><stop offset="0.5" stop-color="#f0b429"/><stop offset="1" stop-color="#e5484d"/>
        </linearGradient>
      </defs>
      <path class="loader__flame" d="M22 76 Q32 100 42 76 Q40 90 32 95 Q24 90 22 76 Z" fill="url(#rg-flame)"/>
      <path d="M32 6 Q48 26 48 56 L48 76 L16 76 L16 56 Q16 26 32 6 Z" fill="url(#rg-body)" stroke="#242b36" stroke-width="1.5"/>
      <circle cx="32" cy="38" r="7" fill="#22c997" stroke="#0e1116" stroke-width="2"/>
      <circle cx="32" cy="38" r="2.5" fill="#fff" opacity="0.6"/>
      <path d="M16 60 L4 78 L16 78 Z" fill="#22c997"/>
      <path d="M48 60 L60 78 L48 78 Z" fill="#22c997"/>
      <circle cx="32" cy="8" r="2" fill="#e5484d"/>
    </svg>`;

  function loaderScene(label, symbol, phrases) {
    const heights = [22, 34, 28, 46, 40, 58, 52, 70, 84];
    const dirs    = ["up", "up", "down", "up", "down", "up", "down", "up", "up"];
    const candles = heights.map((h, i) =>
      `<span class="candle ${dirs[i]}" style="--h:${h}px;--d:${(i * 0.09).toFixed(2)}s">` +
      `<i class="candle__wick"></i><i class="candle__body"></i></span>`).join("");
    const sparks = [12, 30, 52, 68, 82, 92].map((x, i) =>
      `<span class="spark" style="left:${x}%;--sd:${(i * 0.45).toFixed(2)}s;--sx:${i % 2 ? 7 : -7}px"></span>`).join("");
    const ph = (phrases || []).slice(0, 3);
    const ticker = ph.length
      ? `<div class="loader__ticker">${ph.map((p, i) =>
          `<span style="animation-delay:${i * 2}s">${escapeHtml(p)}</span>`).join("")}</div>`
      : "";
    return `
      <div class="loader__scene" aria-hidden="true">
        <div class="loader__candles">${candles}</div>
        <svg class="loader__trend" viewBox="0 0 300 150" width="300" height="150" preserveAspectRatio="none">
          <defs>
            <linearGradient id="ld-area" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0" stop-color="#22c997" stop-opacity="0.35"/>
              <stop offset="1" stop-color="#22c997" stop-opacity="0"/>
            </linearGradient>
          </defs>
          <path class="loader__area" d="${TREND_PATH} L282 150 L26 150 Z" fill="url(#ld-area)"/>
          <path class="loader__line" d="${TREND_PATH}"/>
          <circle class="loader__tip" cx="282" cy="24" r="4"/>
        </svg>
        <div class="loader__rocket" style="offset-path:path('${TREND_PATH}');">${ROCKET_SVG}</div>
        <div class="loader__sparks">${sparks}</div>
      </div>
      <div class="loader__text">
        <span class="loader__label">${escapeHtml(label)}</span>
        ${symbol ? `<span class="loader__symbol">${escapeHtml(symbol)}</span>` : ""}
        <span class="loader__dots"><i></i><i></i><i></i></span>
      </div>
      ${ticker}`;
  }

  function startLoader(el, label, symbol, phrases) {
    el.innerHTML = loaderScene(label, symbol, phrases);
    show(el);
  }
  function stopLoader(el) {
    hide(el);
    el.innerHTML = ""; // drop animations so they restart cleanly next time
  }

  function toast(message, kind = "") {
    els.toast.textContent = message;
    els.toast.className = "toast" + (kind ? ` toast--${kind}` : "");
    setTimeout(() => els.toast.classList.add("hidden"), 4000);
  }

  async function jget(url) {
    const r = await fetch(API + url);
    if (!r.ok) {
      const body = await r.json().catch(() => ({}));
      throw new Error(body.detail || `Request failed (${r.status})`);
    }
    return r.json();
  }
  async function jpost(url, body) {
    const r = await fetch(API + url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!r.ok) {
      const data = await r.json().catch(() => ({}));
      throw new Error(data.detail || `Request failed (${r.status})`);
    }
    return r.json();
  }

  // -------------------- Autocomplete -------------------
  // Attach a Yahoo-search-backed autocomplete dropdown to an <input>.
  // `listEl` is the sibling .ac-list div to render into.
  // `onSelect(item)` fires when the user picks one (click or Enter).
  function attachAutocomplete(input, listEl, onSelect) {
    let activeIdx = -1;
    let items = [];
    let lastQuery = "";
    let debounceTimer = null;
    let inflight = null;

    function hide() {
      listEl.classList.add("hidden");
      activeIdx = -1;
    }

    function highlight(text, q) {
      if (!q) return escapeHtml(text);
      const re = new RegExp("(" + q.replace(/[.*+?^${}()|[\]\\]/g, "\\$&") + ")", "ig");
      return escapeHtml(text).replace(re, "<mark>$1</mark>");
    }

    function render() {
      if (!items.length) {
        listEl.innerHTML = `<div class="ac-empty">No matching NSE stocks.</div>`;
        listEl.classList.remove("hidden");
        return;
      }
      listEl.innerHTML = items.map((it, i) => `
        <div class="ac-item ${i === activeIdx ? "is-active" : ""}" data-idx="${i}" role="option">
          <div class="ac-item__top">
            <span class="ac-item__sym">${highlight(it.symbol, lastQuery)}</span>
            <span class="ac-item__badge">${it.exchange}</span>
          </div>
          <div class="ac-item__name">${highlight(it.name, lastQuery)}</div>
        </div>
      `).join("");
      listEl.classList.remove("hidden");
    }

    function select(item) {
      input.value = item.symbol;
      hide();
      onSelect && onSelect(item);
    }

    async function query(q) {
      if (q.length < 2) {
        items = [];
        hide();
        return;
      }
      if (inflight) inflight.abort();
      inflight = new AbortController();
      try {
        const r = await fetch(`/api/search?q=${encodeURIComponent(q)}&limit=8`, {
          signal: inflight.signal,
        });
        if (!r.ok) return;
        const data = await r.json();
        if (q !== lastQuery) return; // a newer keystroke already ran
        items = data.results || [];
        activeIdx = items.length ? 0 : -1;
        render();
      } catch (_) {
        /* aborted or network — ignore */
      }
    }

    input.addEventListener("input", () => {
      const q = input.value.trim();
      lastQuery = q;
      clearTimeout(debounceTimer);
      debounceTimer = setTimeout(() => query(q), 220);
    });

    input.addEventListener("keydown", (e) => {
      if (listEl.classList.contains("hidden") || !items.length) return;
      if (e.key === "ArrowDown") {
        e.preventDefault();
        activeIdx = (activeIdx + 1) % items.length;
        render();
      } else if (e.key === "ArrowUp") {
        e.preventDefault();
        activeIdx = (activeIdx - 1 + items.length) % items.length;
        render();
      } else if (e.key === "Enter") {
        if (activeIdx >= 0 && activeIdx < items.length) {
          e.preventDefault();
          e.stopPropagation();
          select(items[activeIdx]);
        }
      } else if (e.key === "Escape") {
        hide();
      }
    });

    listEl.addEventListener("mousedown", (e) => {
      // mousedown (not click) so it fires before the input's blur handler
      const el = e.target.closest(".ac-item");
      if (!el) return;
      e.preventDefault();
      const idx = parseInt(el.dataset.idx, 10);
      if (!Number.isNaN(idx) && items[idx]) select(items[idx]);
    });

    input.addEventListener("blur", () => {
      // small delay so a click inside listEl still registers
      setTimeout(hide, 120);
    });

    input.addEventListener("focus", () => {
      const q = input.value.trim();
      if (q.length >= 2 && items.length) render();
    });
  }

  // -------------------- Tabs ---------------------------
  els.tabs.forEach((tab) => {
    tab.addEventListener("click", () => {
      const target = tab.dataset.tab;
      els.tabs.forEach((t) => {
        const active = t === tab;
        t.classList.toggle("is-active", active);
        t.setAttribute("aria-selected", active ? "true" : "false");
      });
      Object.entries(els.panels).forEach(([key, panel]) => {
        panel.classList.toggle("hidden", key !== target);
      });
    });
  });

  // ============================================================
  // FEATURE 1 — Single stock lookup
  // ============================================================

  els.lookupBtn.addEventListener("click", () => runLookup());
  els.lookupInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && els.lookupAc.classList.contains("hidden")) {
      runLookup();
    }
  });

  attachAutocomplete(els.lookupInput, els.lookupAc, (item) => {
    els.lookupInput.value = item.symbol;
    runLookup();
  });

  // Wire autocomplete onto each compare input too.
  els.compareInputs.forEach((input) => {
    const list = input.parentElement.querySelector(".ac-list");
    if (list) {
      attachAutocomplete(input, list, (item) => {
        input.value = item.symbol;
      });
    }
  });

  els.rangeToggle.addEventListener("click", (e) => {
    const btn = e.target.closest(".range-btn");
    if (!btn) return;
    [...els.rangeToggle.querySelectorAll(".range-btn")].forEach((b) =>
      b.classList.toggle("is-active", b === btn)
    );
    state.currentRange = btn.dataset.range;
    if (state.currentSymbol) loadChart(state.currentSymbol, state.currentRange);
  });

  async function runLookup() {
    const value = els.lookupInput.value.trim();
    if (!value) {
      toast("Enter a stock symbol first.", "error");
      return;
    }
    els.lookupBtn.disabled = true;
    els.lookupBtn.textContent = "Analysing…";

    // Show the animated loader with the symbol; hide everything else.
    hide(els.lookupState);
    hide(els.lookupResult);
    startLoader(els.lookupLoader, "Scanning the market for", value.toUpperCase(), [
      "Crunching the fundamentals…",
      "Interrogating the balance sheet…",
      "Asking the bulls for a hot tip…",
    ]);

    try {
      const data = await jget(`/api/stock/${encodeURIComponent(value)}`);
      state.currentSymbol = value;
      renderLookup(data);
      stopLoader(els.lookupLoader);
      show(els.lookupResult);
      loadChart(value, state.currentRange);
    } catch (err) {
      stopLoader(els.lookupLoader);
      show(els.lookupState);
      toast(err.message || "Lookup failed.", "error");
    } finally {
      els.lookupBtn.disabled = false;
      els.lookupBtn.textContent = "Analyse";
    }
  }

  function renderLookup(data) {
    const f = data.fundamentals;
    els.lookupName.textContent = data.name || data.symbol;
    els.lookupSymbol.textContent = `NSE: ${data.symbol}`;
    els.lookupSector.textContent = data.sector
      ? `${data.sector}${data.industry ? " · " + data.industry : ""}`
      : "Sector N/A";

    renderAbout(data);
    renderProsCons(data);
    renderNews(data);

    els.lookupPrice.textContent = f.current_price !== null && f.current_price !== undefined
      ? "₹ " + Number(f.current_price).toLocaleString("en-IN", { maximumFractionDigits: 2 })
      : "—";

    // -------- Group 1: Valuation --------
    els.groupValuation.innerHTML = [
      { label: "Market Cap", value: fmtCr(f.market_cap_cr) },
      { label: "Stock P/E", value: f.pe !== null ? f.pe.toFixed(2) : "—",
        sub: f.forward_pe ? `Fwd: ${f.forward_pe.toFixed(2)}` : "" },
      { label: "Sectoral P/E", value: f.sector_pe !== null ? f.sector_pe.toFixed(2) : "—",
        sub: f.sector_index || "" },
      { label: "PEG Ratio", value: f.peg !== null ? f.peg.toFixed(2) : "—",
        sub: f.peg !== null ? pegHint(f.peg) : "" },
    ].map(statCard).join("");

    // -------- Group 2: Profitability & Quality --------
    const pio = f.piotroski ? `${f.piotroski.score} / ${f.piotroski.max}` : "—";
    els.groupProfit.innerHTML = [
      { label: "ROCE", value: f.roce !== null ? f.roce.toFixed(2) + "%" : "—" },
      { label: "ROE", value: f.roe !== null ? f.roe.toFixed(2) + "%" : "—" },
      { label: "Piotroski", value: pio,
        sub: f.piotroski ? piotroskiHint(f.piotroski.score) : "" },
    ].map(statCard).join("");

    // -------- Group 3: Financial Health --------
    const altman = f.altman_z ? f.altman_z.score : null;
    const altmanZone = f.altman_z ? f.altman_z.zone : null;
    els.groupHealth.innerHTML = [
      { label: "Debt / Equity", value: f.debt_to_equity !== null ? f.debt_to_equity.toFixed(2) : "—",
        sub: f.debt_to_equity !== null ? deHint(f.debt_to_equity) : "" },
      { label: "Altman Z", value: altman !== null ? formatAltman(altman) : "—",
        pill: altmanZone ? { text: altmanZone, kind: altmanZoneKind(altmanZone) } : null },
    ].map(statCard).join("");

    // -------- Group 4: Returns --------
    els.groupReturns.innerHTML = [
      { label: "1 Day",  value: fmtPct(data.returns?.["1d"]), trend: data.returns?.["1d"] },
      { label: "1 Week", value: fmtPct(data.returns?.["1w"]), trend: data.returns?.["1w"] },
      { label: "1 Month", value: fmtPct(data.returns?.["1m"]), trend: data.returns?.["1m"] },
      { label: "1 Year",  value: fmtPct(data.returns?.["1y"]), trend: data.returns?.["1y"] },
      { label: "5 Years", value: fmtPct(data.returns?.["5y"]), trend: data.returns?.["5y"] },
    ].map(statCard).join("");

    // -------- Group 5: Shareholding (with change vs last quarter) --------
    const sh = f.shareholding;
    if (sh) {
      const ch = sh.changes || {};
      els.holdingPeriod.textContent = sh.period
        ? (sh.prev_period ? `${sh.period} · Δ vs ${sh.prev_period}` : `as of ${sh.period}`)
        : "";
      const cells = [
        { label: "Promoter", value: sh.promoter, change: ch.promoter, color: "#22c997" },
        { label: "FII",      value: sh.fii,      change: ch.fii,      color: "#54e6b8" },
        { label: "DII",      value: sh.dii,      change: ch.dii,      color: "#f0b429" },
        { label: "Public",   value: sh.public,   change: ch.public,   color: "#8b95a5" },
      ];
      els.lookupHolding.innerHTML = cells.map((c) => `
        <div class="holding-cell">
          <div class="holding-cell__head">
            <span class="holding-cell__label">${c.label}</span>
            ${holdingDelta(c.change)}
          </div>
          <span class="holding-cell__value">${c.value !== null && c.value !== undefined ? c.value.toFixed(2) + "%" : "—"}</span>
          <div class="holding-bar">
            <div class="holding-bar__fill" style="width:${Math.min(100, c.value || 0)}%; background:${c.color}"></div>
          </div>
        </div>
      `).join("");
    } else {
      els.holdingPeriod.textContent = "";
      els.lookupHolding.innerHTML = `<div class="state" style="grid-column:1/-1; padding:18px;">
        Shareholding data isn't available for this stock right now.
      </div>`;
    }
  }

  // Change pill for shareholding (▲ +0.53 / ▼ -0.71 / flat).
  function holdingDelta(change) {
    if (change === null || change === undefined) return "";
    if (Math.abs(change) < 0.005) {
      return `<span class="holding-delta holding-delta--flat">±0.00</span>`;
    }
    const up = change > 0;
    const cls = up ? "holding-delta--up" : "holding-delta--down";
    const arrow = up ? "▲" : "▼";
    return `<span class="holding-delta ${cls}">${arrow} ${up ? "+" : ""}${change.toFixed(2)}</span>`;
  }

  // -------- About + official links --------
  function renderAbout(data) {
    const about = (data.about || "").trim();
    const website = data.website;
    const industry = data.industry_link;
    if (!about && !website && !industry) {
      els.aboutGroup.hidden = true;
      return;
    }
    els.aboutGroup.hidden = false;
    els.aboutText.textContent = about || "No description available.";

    // Website link sits inline on the section heading.
    if (website) {
      els.aboutWebsite.hidden = false;
      els.aboutWebsite.href = website;
      els.aboutWebsite.textContent = "↗ " + prettyHost(website);
    } else {
      els.aboutWebsite.hidden = true;
    }

    // Industry + exchange links row under the blurb.
    const links = [];
    if (industry && industry.name) {
      links.push(`<a class="about-chip" href="${escapeAttr(industry.url)}" target="_blank" rel="noopener noreferrer">
        <span class="about-chip__k">Industry</span><span class="about-chip__v">${escapeHtml(industry.name)} ↗</span>
      </a>`);
    }
    if (data.sector) {
      links.push(`<span class="about-chip about-chip--static">
        <span class="about-chip__k">Sector</span><span class="about-chip__v">${escapeHtml(data.sector)}</span>
      </span>`);
    }
    els.aboutLinks.innerHTML = links.join("");
  }

  function prettyHost(url) {
    try {
      return new URL(url).hostname.replace(/^www\./, "");
    } catch (_) {
      return url.replace(/^https?:\/\/(www\.)?/, "").replace(/\/$/, "");
    }
  }

  // -------- Pros & Cons --------
  function renderProsCons(data) {
    const pros = data.pros || [];
    const cons = data.cons || [];
    if (!pros.length && !cons.length) {
      els.proconGroup.hidden = true;
      return;
    }
    els.proconGroup.hidden = false;
    els.prosList.innerHTML = pros.length
      ? pros.map((p) => `<li>${escapeHtml(p)}</li>`).join("")
      : `<li class="procon__empty">No notable pros flagged.</li>`;
    els.consList.innerHTML = cons.length
      ? cons.map((c) => `<li>${escapeHtml(c)}</li>`).join("")
      : `<li class="procon__empty">No notable cons flagged.</li>`;
  }

  // -------- Recent news --------
  function renderNews(data) {
    const news = data.news || [];
    if (!news.length) {
      els.newsGroup.hidden = true;
      return;
    }
    els.newsGroup.hidden = false;
    els.newsList.innerHTML = news.map((n) => {
      const when = relativeTime(n.published);
      const meta = [n.publisher, when].filter(Boolean).join(" · ");
      const inner = `
        <span class="news-item__title">${escapeHtml(n.title)}</span>
        <span class="news-item__meta">${escapeHtml(meta)}</span>`;
      return n.link
        ? `<a class="news-item" href="${escapeAttr(n.link)}" target="_blank" rel="noopener noreferrer">${inner}<span class="news-item__arrow">↗</span></a>`
        : `<div class="news-item">${inner}</div>`;
    }).join("");
  }

  function relativeTime(iso) {
    if (!iso) return "";
    const then = new Date(iso);
    if (Number.isNaN(then.getTime())) return "";
    const days = Math.floor((Date.now() - then.getTime()) / 86400000);
    if (days <= 0) return "today";
    if (days === 1) return "yesterday";
    if (days < 7) return `${days}d ago`;
    if (days < 30) return `${Math.floor(days / 7)}w ago`;
    return then.toLocaleDateString("en-IN", { day: "2-digit", month: "short" });
  }

  function escapeAttr(s) {
    return escapeHtml(s);
  }

  function statCard({ label, value, sub, trend, pill }) {
    const trendCls = trend !== undefined ? trendClass(trend) : "";
    const valueCls = value === "—" ? "stat__value--na" : trendCls;
    const pillHtml = pill ? `<span class="stat__pill stat__pill--${pill.kind}">${pill.text}</span>` : "";
    const subHtml = sub ? `<span class="stat__sub">${sub}</span>` : "";
    return `
      <div class="stat">
        <span class="stat__label">${label}</span>
        <span class="stat__value ${valueCls}">${value}</span>
        ${pillHtml || subHtml}
      </div>
    `;
  }

  function piotroskiHint(score) {
    if (score >= 7) return "Strong";
    if (score >= 4) return "Average";
    return "Weak";
  }
  function altmanZoneKind(zone) {
    if (zone === "Safe") return "safe";
    if (zone === "Grey") return "grey";
    return "danger";
  }
  function pegHint(peg) {
    if (peg < 0) return "Negative growth";
    if (peg < 1) return "Undervalued";
    if (peg < 2) return "Fair";
    return "Expensive";
  }
  function deHint(de) {
    if (de < 0.3) return "Low leverage";
    if (de < 1)   return "Moderate";
    if (de < 2)   return "High";
    return "Very high";
  }
  function formatAltman(z) {
    if (z > 99) return z.toFixed(0); // debt-free firms blow up; keep it readable
    return z.toFixed(2);
  }

  // -------------------- Chart --------------------------
  async function loadChart(symbol, range) {
    els.chartState.textContent = "Loading…";
    els.chartState.classList.remove("hidden");
    try {
      const data = await jget(`/api/stock/${encodeURIComponent(symbol)}/chart?range=${range}`);
      drawChart(data, range);
      els.chartState.classList.add("hidden");
      const ret = data.total_return_pct;
      const color = ret >= 0 ? "var(--accent)" : "var(--danger)";
      els.chartReturn.textContent = fmtPct(ret);
      els.chartReturn.style.color = color;
      const inline = document.getElementById("chartReturnInline");
      if (inline) {
        inline.textContent = `${range.toUpperCase()} return: ${fmtPct(ret)}`;
        inline.style.color = color;
      }
    } catch (err) {
      els.chartState.textContent = err.message || "No data.";
    }
  }

  function drawChart(data, range) {
    if (!window.Chart) {
      els.chartState.textContent = "Chart library not loaded.";
      els.chartState.classList.remove("hidden");
      return;
    }
    const labels = data.series.map((p) => p.t);
    const prices = data.series.map((p) => p.price);
    const up = data.total_return_pct >= 0;
    const color = up ? "#22c997" : "#e5484d";

    if (state.chart) state.chart.destroy();

    const ctx = els.chartCanvas.getContext("2d");
    const gradient = ctx.createLinearGradient(0, 0, 0, els.chartCanvas.height || 260);
    gradient.addColorStop(0, up ? "rgba(34, 201, 151, 0.32)" : "rgba(229, 72, 77, 0.32)");
    gradient.addColorStop(1, "rgba(34, 201, 151, 0)");

    state.chart = new Chart(ctx, {
      type: "line",
      data: {
        labels,
        datasets: [{
          label: data.symbol,
          data: prices,
          borderColor: color,
          backgroundColor: gradient,
          borderWidth: 2,
          fill: true,
          tension: 0.25,
          pointRadius: 0,
          pointHoverRadius: 4,
          pointHoverBackgroundColor: color,
        }],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: { intersect: false, mode: "index" },
        plugins: {
          legend: { display: false },
          tooltip: {
            backgroundColor: "#161b22",
            borderColor: "#242b36",
            borderWidth: 1,
            titleColor: "#e6edf3",
            bodyColor: "#e6edf3",
            padding: 10,
            displayColors: false,
            callbacks: {
              title: (items) => formatTooltipTitle(items[0].label, range),
              label: (item) => "₹ " + Number(item.raw).toFixed(2),
            },
          },
        },
        scales: {
          x: {
            ticks: {
              color: "#8b95a5",
              maxTicksLimit: 6,
              callback: function (v, i) {
                return formatAxisLabel(labels[i], range);
              },
            },
            grid: { color: "rgba(255,255,255,0.04)" },
          },
          y: {
            ticks: { color: "#8b95a5", callback: (v) => "₹" + v },
            grid: { color: "rgba(255,255,255,0.04)" },
          },
        },
      },
    });
  }

  function formatTooltipTitle(iso, range) {
    const d = new Date(iso);
    if (range === "1d" || range === "1w") {
      return d.toLocaleString("en-IN", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" });
    }
    return d.toLocaleDateString("en-IN", { day: "2-digit", month: "short", year: "numeric" });
  }
  function formatAxisLabel(iso, range) {
    const d = new Date(iso);
    if (range === "1d") return d.toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit" });
    if (range === "1w" || range === "1m") return d.toLocaleDateString("en-IN", { day: "2-digit", month: "short" });
    return d.toLocaleDateString("en-IN", { month: "short", year: "2-digit" });
  }

  // ============================================================
  // FEATURE 2 — Compare
  // ============================================================

  els.compareBtn.addEventListener("click", runCompare);
  els.compareClearBtn.addEventListener("click", () => {
    els.compareInputs.forEach((i) => (i.value = ""));
    hide(els.compareResult);
    show(els.compareState);
  });

  async function runCompare() {
    const symbols = [...els.compareInputs].map((i) => i.value.trim()).filter(Boolean);
    if (symbols.length < 2) {
      toast("Add at least two stocks to compare.", "error");
      return;
    }
    els.compareBtn.disabled = true;
    els.compareBtn.textContent = "Comparing…";
    hide(els.compareState);
    hide(els.compareResult);
    startLoader(els.compareLoader, "Sizing up", symbols.map((s) => s.toUpperCase()).join(" vs "), [
      "Lining up the contenders…",
      "Weighing P/E against pride…",
      "Letting the numbers duke it out…",
    ]);
    try {
      const data = await jpost("/api/compare", { symbols });
      renderCompare(data);
      stopLoader(els.compareLoader);
      show(els.compareResult);
    } catch (err) {
      stopLoader(els.compareLoader);
      show(els.compareState);
      toast(err.message || "Compare failed.", "error");
    } finally {
      els.compareBtn.disabled = false;
      els.compareBtn.textContent = "Compare";
    }
  }

  function renderCompare(data) {
    if (!data.stocks.length) {
      toast("None of those symbols resolved on NSE.", "error");
      return;
    }
    const { stocks, rows, verdict, unresolved } = data;

    // Verdict card
    const winners = verdict?.winners || [];
    const badge = stocks.find((s) => s.symbol === winners[0])?.symbol?.slice(0, 2) || "—";
    els.compareVerdict.innerHTML = `
      <div class="verdict__badge">${badge}</div>
      <div class="verdict__body">
        <span class="verdict__title">${winners.length > 1 ? "It's a tie" : "Winner: " + winnerName(stocks, winners[0])}</span>
        <span class="verdict__summary">${verdict.summary}</span>
        ${unresolved.length ? `<span class="verdict__summary" style="color:var(--danger);">Couldn't resolve: ${unresolved.join(", ")}</span>` : ""}
      </div>
    `;

    // Table
    const thead = `<tr>
      <th>Metric</th>
      ${stocks.map((s) => `<th>${s.symbol}<div style="font-size:11px;color:var(--text-mute);font-weight:500;margin-top:2px;text-transform:none;letter-spacing:0;">${escapeHtml(s.name || "")}</div></th>`).join("")}
    </tr>`;
    els.cmpTable.querySelector("thead").innerHTML = thead;

    const body = rows.map((row) => {
      const cells = row.values.map((v, idx) => {
        if (v === null || v === undefined) return `<td class="value value--na">—</td>`;
        const isWinner = idx === row.winner_index;
        return `<td class="value ${isWinner ? "value--winner" : ""}">${formatCompareValue(row.key, v)}</td>`;
      }).join("");
      return `<tr><td class="metric">${row.label}</td>${cells}</tr>`;
    }).join("");
    els.cmpTable.querySelector("tbody").innerHTML = body;
  }

  function winnerName(stocks, sym) {
    const s = stocks.find((x) => x.symbol === sym);
    return s ? `${s.name} (${s.symbol})` : sym;
  }
  function formatCompareValue(key, v) {
    if (key === "pe" || key === "peg" || key === "altman_z_score" || key === "debt_to_equity" || key === "sector_pe_relative")
      return Number(v).toFixed(2);
    if (key === "piotroski_score") return `${v} / 9`;
    if (key === "roce" || key === "roe" || key === "promoter" || key === "fii" || key === "dii")
      return Number(v).toFixed(2) + "%";
    return String(v);
  }
  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  }

  // ============================================================
  // FEATURE 3 — OHLC CSV
  // ============================================================

  els.fileBrowseBtn.addEventListener("click", () => els.fileInput.click());
  els.fileInput.addEventListener("change", (e) => {
    const f = e.target.files?.[0];
    if (!f) return;
    state.ohlcFile = f;
    els.fileName.textContent = f.name;
    els.fileDrop.classList.add("is-ready");
    els.ohlcBtn.disabled = false;
  });
  els.ohlcRange.addEventListener("click", (e) => {
    const btn = e.target.closest(".range-btn");
    if (!btn) return;
    [...els.ohlcRange.querySelectorAll(".range-btn")].forEach((b) =>
      b.classList.toggle("is-active", b === btn)
    );
    state.ohlcRange = btn.dataset.range;
  });

  // Drag and drop support
  ["dragover", "dragenter"].forEach((ev) => {
    els.fileDrop.addEventListener(ev, (e) => {
      e.preventDefault();
      els.fileDrop.style.borderColor = "var(--accent)";
    });
  });
  ["dragleave", "drop"].forEach((ev) => {
    els.fileDrop.addEventListener(ev, (e) => {
      e.preventDefault();
      els.fileDrop.style.borderColor = "";
    });
  });
  els.fileDrop.addEventListener("drop", (e) => {
    const f = e.dataTransfer.files?.[0];
    if (!f) return;
    state.ohlcFile = f;
    els.fileName.textContent = f.name;
    els.fileDrop.classList.add("is-ready");
    els.ohlcBtn.disabled = false;
  });

  els.ohlcBtn.addEventListener("click", async () => {
    if (!state.ohlcFile) return;
    els.ohlcBtn.disabled = true;
    els.ohlcBtn.textContent = "Fetching data…";
    hide(els.ohlcState);
    startLoader(els.ohlcLoader, "Mining OHLC history", state.ohlcRange.toUpperCase(), [
      "Digging through years of candles…",
      "Stacking Open · High · Low · Close…",
      "Bribing the data gods…",
    ]);
    try {
      const fd = new FormData();
      fd.append("file", state.ohlcFile);
      fd.append("range", state.ohlcRange);
      const r = await fetch("/api/ohlc/csv", { method: "POST", body: fd });
      if (!r.ok) {
        const data = await r.json().catch(() => ({}));
        throw new Error(data.detail || `Failed (${r.status})`);
      }
      const summary = r.headers.get("X-Bullrun-Summary") || "";
      const blob = await r.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `bullrun_ohlc_${state.ohlcRange}.csv`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
      toast(`Downloaded · ${summary}`, "success");
    } catch (err) {
      toast(err.message || "OHLC download failed.", "error");
    } finally {
      stopLoader(els.ohlcLoader);
      show(els.ohlcState);
      els.ohlcBtn.disabled = false;
      els.ohlcBtn.textContent = "Generate & Download";
    }
  });

  // -------------------- Deep link (?q=SYMBOL) ----------
  // Lets you share a direct link to a stock, e.g. /?q=RELIANCE
  (function deepLink() {
    const q = new URLSearchParams(location.search).get("q");
    if (q) {
      els.lookupInput.value = q;
      runLookup();
    }
  })();
})();
