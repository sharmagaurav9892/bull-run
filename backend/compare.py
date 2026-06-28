"""
Compare 2..4 stocks across the same fundamentals and pick a winner per metric
+ an overall verdict.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from .fundamentals import get_fundamentals

# (metric_key, label, direction)
# direction: "low" -> lower is better, "high" -> higher is better.
_METRICS = [
    ("pe", "Stock P/E", "low"),
    ("sector_pe_relative", "P/E vs Sector", "low"),
    ("roce", "ROCE %", "high"),
    ("roe", "ROE %", "high"),
    ("debt_to_equity", "Debt / Equity", "low"),
    ("piotroski_score", "Piotroski (0-9)", "high"),
    ("peg", "PEG Ratio", "low"),
    ("altman_z_score", "Altman Z", "high"),
    ("promoter", "Promoter %", "high"),
    ("fii", "FII %", "high"),
    ("dii", "DII %", "high"),
]


def _flat(stock: Dict[str, Any]) -> Dict[str, Optional[float]]:
    f = stock["fundamentals"]
    sh = f.get("shareholding") or {}
    pio = f.get("piotroski") or {}
    alt = f.get("altman_z") or {}
    pe = f.get("pe")
    sector_pe = f.get("sector_pe")
    rel = (pe / sector_pe) if (pe is not None and sector_pe) else None
    return {
        "pe": pe,
        "sector_pe_relative": rel,
        "roce": f.get("roce"),
        "roe": f.get("roe"),
        "debt_to_equity": f.get("debt_to_equity"),
        "piotroski_score": pio.get("score"),
        "peg": f.get("peg"),
        "altman_z_score": alt.get("score"),
        "promoter": sh.get("promoter"),
        "fii": sh.get("fii"),
        "dii": sh.get("dii"),
    }


def build_comparison(symbols: List[str]) -> Dict[str, Any]:
    raw_stocks: List[Optional[Dict[str, Any]]] = [get_fundamentals(s) for s in symbols]

    resolved: List[Dict[str, Any]] = []
    unresolved: List[str] = []
    for original, stock in zip(symbols, raw_stocks):
        if stock is None:
            unresolved.append(original)
        else:
            resolved.append(stock)

    if not resolved:
        return {"stocks": [], "unresolved": unresolved, "rows": [], "verdict": None}

    # Build a row per metric with per-stock values + the winner.
    rows = []
    wins = {s["symbol"]: 0 for s in resolved}
    flats = [_flat(s) for s in resolved]

    for key, label, direction in _METRICS:
        values = [f.get(key) for f in flats]
        numeric = [(idx, v) for idx, v in enumerate(values) if v is not None]
        winner_idx = None
        if numeric:
            if direction == "high":
                winner_idx = max(numeric, key=lambda kv: kv[1])[0]
            else:
                # For "low" metrics, ignore non-positive values where they don't
                # make sense (e.g. negative P/E from loss-making companies).
                pos = [(i, v) for i, v in numeric if v > 0]
                pick_from = pos or numeric
                winner_idx = min(pick_from, key=lambda kv: kv[1])[0]
            wins[resolved[winner_idx]["symbol"]] += 1

        rows.append(
            {
                "key": key,
                "label": label,
                "direction": direction,
                "values": values,
                "winner_index": winner_idx,
            }
        )

    # Overall verdict = stock with the most wins; ties broken by sum of normalised wins.
    ranking = sorted(
        ((s["symbol"], wins[s["symbol"]]) for s in resolved),
        key=lambda kv: kv[1],
        reverse=True,
    )
    top_score = ranking[0][1] if ranking else 0
    leaders = [sym for sym, w in ranking if w == top_score]

    verdict = {
        "winners": leaders,
        "tie": len(leaders) > 1,
        "wins_by_symbol": wins,
        "summary": _summary(resolved, wins, leaders),
    }

    return {
        "stocks": [
            {
                "symbol": s["symbol"],
                "name": s["name"],
                "sector": s.get("sector"),
                "fundamentals": s["fundamentals"],
                "returns": s.get("returns"),
            }
            for s in resolved
        ],
        "unresolved": unresolved,
        "rows": rows,
        "verdict": verdict,
    }


def _summary(stocks, wins, leaders) -> str:
    by_sym = {s["symbol"]: s for s in stocks}
    leader_names = ", ".join(by_sym[s]["name"] for s in leaders)
    if len(leaders) == 1:
        s = by_sym[leaders[0]]
        return (
            f"On the 11 fundamentals compared, {s['name']} ({s['symbol']}) wins "
            f"{wins[s['symbol']]} categories — the strongest blend of valuation, "
            "returns, and balance-sheet quality in this set."
        )
    return (
        f"It's a tie. {leader_names} share the lead with "
        f"{wins[leaders[0]]} category wins each — pick based on the rows that "
        "matter most to you."
    )
