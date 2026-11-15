"""AI investigator: hypotheses -> requested analyses -> challenge -> labelled discoveries.

Deterministic and reproducible (no language model at run time, matching the AI layer's current
release). Each hypothesis names the tools it calls, the evidence they returned, the challenge it
faced, and a status:
  supported    - passes the statistical test after correction for multiple cells AND the challenge
  exploratory  - interesting but not corrected-significant, or fails the challenge
  not supported
Findings carry the ids and locations of the cells involved so the frontend can highlight them,
never the cells' time series.
"""

from __future__ import annotations

import threading
from functools import lru_cache

from . import tools
from .grid import load_grid

CAVEATS = [
    "Nighttime land surface temperature, not air temperature; no causes are claimed.",
    ("Monthly values are serially correlated, so p and q values are likely smaller than they would "
    "be under an autocorrelation-adjusted test; statuses use the both-halves challenge as a guard."),
    ("Neighbouring cells are spatially correlated; Benjamini-Hochberg remains valid under positive "
    "dependence but adjacent cells are not independent discoveries."),
    "Historical description of 2003-2024; not a forecast.",
]


def _cells(rows, metric_key):
    return [{**{k: r[k] for k in ("id", "lat", "lon", "quarter", "footprint")}, "metric": r[metric_key],
             "q": r.get("q")} for r in rows]


def h1_widespread() -> dict:
    trends = tools.all_cell_trends()
    rows = trends["cells"]
    warm = [r for r in rows if r["significant_fdr"] and r["slope_per_year"] > 0]
    challenge = [r for r in warm if all(h.get("slope_per_year", 0) > 0 for h in tools.cell_trend(r["id"])["halves"])]
    status = "supported" if warm and len(challenge) >= 0.8 * len(warm) else ("exploratory" if warm else "not_supported")
    return {
        "id": "widespread-warming",
        "hypothesis": "The warming is not an artefact of averaging: individual cells warm too.",
        "tools": ["all_cell_trends", "cell_trend"],
        "status": status,
        "statement": (f"{len(warm)} of {trends['tested']} cells show statistically significant nighttime "
                      f"warming after false-discovery-rate correction (q < {tools.ALPHA}); "
                      f"{len(challenge)} of them also warm in both 2003–2013 and 2014–2024."),
        "challenge": "Re-estimated each significant cell's slope separately in both halves of the record.",
        "evidence": {"tested": trends["tested"], "significant_warming": len(warm),
                     "significant_cooling": sum(r["significant_fdr"] and r["slope_per_year"] < 0 for r in rows),
                     "warming_in_both_halves": len(challenge)},
        "highlight": "none",
        "cells": [],
    }


def h2_heterogeneity() -> dict:
    stats = {rid: tools.region_vs_cells(rid) for rid in
             ("phoenix_northwest", "phoenix_northeast", "phoenix_southwest", "phoenix_southeast")}
    rows = tools.all_cell_trends()["cells"]
    slopes = sorted(rows, key=lambda r: r["slope_per_year"])
    lo, hi = slopes[0], slopes[-1]
    return {
        "id": "hidden-spread",
        "hypothesis": "Regional averages conceal a wide range of warming rates underneath.",
        "tools": ["all_cell_trends", "region_vs_cells"],
        "status": "supported" if hi["slope_per_year"] > 2 * lo["slope_per_year"] and lo["significant_fdr"] else "exploratory",
        "statement": (f"Individual cells warm between {lo['slope_per_year']:+.3f} and {hi['slope_per_year']:+.3f} °C "
                      "per year; every quarter's average sits inside a spread of "
                      f"{min(s['cell_slope_per_year']['spread_max_minus_min'] for s in stats.values()):.3f}–"
                      f"{max(s['cell_slope_per_year']['spread_max_minus_min'] for s in stats.values()):.3f} °C/yr."),
        "challenge": "Checked that even the slowest cell's own trend is significant after correction, "
                     "so the spread is between warming rates, not noise around zero.",
        "evidence": {rid: {"regional_slope_per_year": s["regional_trend"]["slope_per_year"],
                           **s["cell_slope_per_year"]} for rid, s in stats.items()},
        "highlight": "extremes",
        "cells": _cells([lo, hi], "slope_per_year"),
    }


def _localized(direction: int) -> dict:
    loc = tools.localized_differences()
    rows = [r for r in loc["cells"] if r["diff_slope_per_year"] * direction > 0]
    supported = [r for r in rows if r["q"] < tools.ALPHA and r["consistent_in_both_halves"]]
    exploratory = [r for r in rows if r["p"] < tools.ALPHA and r not in supported]
    word = "faster" if direction > 0 else "slower"
    by_q = {}
    for r in supported:
        by_q.setdefault(r["quarter"], []).append(r)
    top = sorted(supported, key=lambda r: -abs(r["diff_slope_per_year"]))[:1]
    where = ", ".join(f"{q} {len(v)}" for q, v in sorted(by_q.items(), key=lambda kv: -len(kv[1])))
    statement = (f"{len(supported)} cells warm significantly {word} than their own quarter's average "
                 f"(q < {tools.ALPHA}, same direction in both halves)" + (f": {where}." if where else ".")
                 + (f" The strongest, {top[0]['id']} in the {top[0]['quarter']} quarter, differs by "
                    f"{top[0]['diff_slope_per_year']:+.3f} °C per year." if top else "")
                 + f" {len(exploratory)} more are exploratory only.")
    return {
        "id": f"local-{word}",
        "hypothesis": f"Some neighbourhoods warm {word} than the regional average suggests.",
        "tools": ["localized_differences"],
        "status": "supported" if supported else ("exploratory" if exploratory else "not_supported"),
        "statement": statement,
        "challenge": "Tested each cell's difference from its quarter, corrected across all 192 cells "
                     "(Benjamini-Hochberg), then required the same direction in 2003–2013 and 2014–2024.",
        "evidence": {"tested": loc["tested"], "supported": len(supported), "exploratory": len(exploratory)},
        "highlight": word,
        "cells": _cells(supported, "diff_slope_per_year"),
        "exploratory_cells": _cells(exploratory, "diff_slope_per_year"),
    }


def h5_seasons() -> dict:
    results = [tools.seasonal_trend("phoenix_study_area", s) for s in tools.SEASONS]
    qs = tools.bh_qvalues([r["p"] for r in results])
    for r, q in zip(results, qs):
        r["q"] = q
    sig = [r for r in results if r["q"] < tools.ALPHA]
    strongest = max(results, key=lambda r: r["slope_per_year"])
    weakest = min(results, key=lambda r: r["slope_per_year"])
    return {
        "id": "seasons",
        "hypothesis": "Nights warm faster in some seasons than others.",
        "tools": ["seasonal_trend"],
        "status": "supported" if strongest in sig else "exploratory",
        "statement": (f"Across the whole study area, {strongest['season_name']} nights warm fastest "
                      f"({strongest['slope_per_year']:+.3f} °C/yr, q = {strongest['q']:.2g}) and "
                      f"{weakest['season_name']} nights slowest ({weakest['slope_per_year']:+.3f} °C/yr, "
                      f"q = {weakest['q']:.2g}). {len(sig)} of 4 seasonal trends are significant after correction."),
        "challenge": "Corrected across the four seasons; the slopes are compared descriptively, "
                     "no test of the difference between seasons is claimed.",
        "evidence": {r["season"]: {k: r[k] for k in ("slope_per_year", "p", "q", "tau")} | {"years": len(r["years_used"])}
                     for r in results},
        "highlight": "none",
        "cells": [],
    }


def h6_anomalies() -> dict:
    an = tools.anomalies(threshold=4.0, limit=10)
    return {
        "id": "unusual-months",
        "hypothesis": "Some individual cell-months are far outside their usual range.",
        "tools": ["anomalies"],
        "status": "exploratory",
        "statement": (f"{an['count']} cell-months sit at least 4 robust standard deviations from that cell's "
                      "usual value for the calendar month. These are leads to inspect, not findings."),
        "challenge": "None applied: anomaly screening is descriptive and is always reported as exploratory.",
        "evidence": {"threshold": 4.0, "count": an["count"],
                     "examples": [{k: a[k] for k in ("id", "month", "value", "calendar_month_median", "robust_z")}
                                  for a in an["anomalies"]]},
        "highlight": "anomalies",
        "cells": [{**{k: a[k] for k in ("id", "lat", "lon", "quarter", "footprint")}, "metric": a["robust_z"],
                   "month": a["month"]} for a in an["anomalies"]],
    }


PERIOD = "2003-01 to 2024-12 (264 months)"
SOURCE = "NASA Terra MODIS MOD11C3 v061 LST_Night_CMG, qc-v1, 0.05° grid cells"
DETAILS = {
    "widespread-warming": {
        "title": "Warming shows up in individual cells, not only in the averages",
        "location": "All 192 cells of the Phoenix study window",
        "method": "Seasonal Mann-Kendall + seasonal Sen's slope per cell; Benjamini-Hochberg FDR across 192 cells; "
                  "challenge: slope sign in each half of the record",
        "limitations": "A significant trend in every cell does not mean every cell warms at the same rate; serial "
                       "correlation makes q-values optimistic.",
        "next_question": "Which cells lose their warming in one half of the record, and is that a data gap or a real change?"},
    "hidden-spread": {
        "title": "Regional averages hide a wide range of cell warming rates",
        "location": "Slowest and fastest cells (highlighted)",
        "method": "Per-cell seasonal Sen's slope compared with each quarter's published slope",
        "limitations": "Describes spread; does not test whether any two particular cells differ.",
        "next_question": "Do the fastest cells cluster together, and do they share land-cover change?"},
    "local-faster": {
        "title": "Pockets of Phoenix warm faster than their own quarter",
        "location": "Highlighted cells",
        "method": "Seasonal Mann-Kendall on each cell minus its quarter's published series; Benjamini-Hochberg FDR; "
                  "same-direction challenge in both halves",
        "limitations": "Adjacent cells are correlated, so a cluster is one pattern, not many independent discoveries. "
                       "No cause (for example new development) is established.",
        "next_question": "Do these cells coincide with areas that urbanised after 2003?"},
    "local-slower": {
        "title": "Some neighbourhoods warm more slowly than their quarter",
        "location": "Highlighted cells",
        "method": "Seasonal Mann-Kendall on each cell minus its quarter's published series; Benjamini-Hochberg FDR; "
                  "same-direction challenge in both halves",
        "limitations": "Slower is still warming in every case; the difference is relative to the quarter average.",
        "next_question": "Are the slower cells parks, farmland or mountain terrain?"},
    "seasons": {
        "title": "Nights warm at different rates in different seasons",
        "location": "Whole Phoenix study area",
        "method": "Mann-Kendall + Sen's slope on yearly seasonal means (complete seasons only); Benjamini-Hochberg "
                  "across the four seasons",
        "limitations": "The seasonal slopes are compared descriptively; no direct test of summer minus winter yet.",
        "next_question": "Is the summer-minus-winter difference itself a significant trend?"},
    "unusual-months": {
        "title": "A few cell-months sit far outside their normal range",
        "location": "Cells and months listed in the evidence",
        "method": "Robust z-score against each cell's calendar-month median (median absolute deviation)",
        "limitations": "Screening only. Unusual months may reflect real events or residual data artefacts.",
        "next_question": "Do the most extreme months line up with known heat waves or sensor issues?"},
}


def _confidence(f: dict) -> str:
    if f["status"] == "supported":
        return "Statistically supported: significant after correction and survived its challenge"
    if f["status"] == "exploratory":
        return "Exploratory: interesting, but not corrected-significant or did not survive its challenge"
    return "Not supported by the tests run"


def _evidence_text(f: dict) -> str:
    e = f.get("evidence", {})
    if f["id"] == "seasons":
        return "; ".join(f"{k}: {v['slope_per_year']:+.3f} °C/yr (q = {v['q']:.2g}, {v['years']} years)" for k, v in e.items())
    if f["id"] == "hidden-spread":
        return "; ".join(f"{k.replace('phoenix_', '')}: cells {v['min']:+.3f} to {v['max']:+.3f}, quarter "
                         f"{v['regional_slope_per_year']:+.3f} °C/yr" for k, v in e.items())
    if f["id"] == "unusual-months":
        return "; ".join(f"{x['id']} {x['month']}: {x['value']:.1f} °C vs usual {x['calendar_month_median']:.1f} "
                         f"(z = {x['robust_z']:+.1f})" for x in e.get("examples", [])[:5])
    return ", ".join(f"{k.replace('_', ' ')}: {v}" for k, v in e.items())


def _computed_details(f: dict) -> dict:
    """Parts of titles/locations that depend on the numbers are computed, never hard-coded."""
    out = {}
    if f["id"] == "hidden-spread" and len(f["cells"]) == 2:
        lo, hi = sorted(c["metric"] for c in f["cells"])
        if lo > 0:
            out["title"] = f"Regional averages hide a {hi / lo:.1f}-fold range of cell warming rates"
    if f["id"] == "seasons":
        ev = f["evidence"]
        names = {"DJF": "winter", "MAM": "spring", "JJA": "summer", "SON": "autumn"}
        fast = max(ev, key=lambda k: ev[k]["slope_per_year"])
        slow = min(ev, key=lambda k: ev[k]["slope_per_year"])
        if ev[slow]["slope_per_year"] > 0:
            ratio = ev[fast]["slope_per_year"] / ev[slow]["slope_per_year"]
            out["title"] = f"{names[fast].capitalize()} nights are warming {ratio:.1f}× as fast as {names[slow]} nights"
    if f["id"] in ("local-faster", "local-slower") and f["cells"]:
        counts = {}
        for c in f["cells"]:
            counts[c["quarter"]] = counts.get(c["quarter"], 0) + 1
        out["location"] = f"{len(f['cells'])} highlighted cells: " + ", ".join(
            f"{q} {n}" for q, n in sorted(counts.items(), key=lambda kv: -kv[1]))
    out["summary"] = _summary(f)
    return out


def _summary(f: dict) -> str:
    """One plain sentence for the card, built from the same numbers as the statement."""
    ev, cells = f.get("evidence", {}), f.get("cells", [])
    if f["id"] == "widespread-warming":
        cooled = "none show cooling" if ev['significant_cooling'] == 0 else f"{ev['significant_cooling']} show cooling"
        return f"{ev['significant_warming']} of {ev['tested']} cells show significant nighttime warming; {cooled}."
    if f["id"] == "hidden-spread" and len(cells) == 2:
        lo, hi = sorted(c["metric"] for c in cells)
        return f"The slowest cell warms {lo:+.3f} °C a year, the fastest {hi:+.3f}."
    if f["id"] in ("local-faster", "local-slower"):
        word = "faster" if f["id"] == "local-faster" else "slower"
        return f"{ev['supported']} neighbourhood cells warm {word} than the quarter around them."
    if f["id"] == "seasons":
        names = {"DJF": "winter", "MAM": "spring", "JJA": "summer", "SON": "autumn"}
        fast = max(ev, key=lambda k: ev[k]["slope_per_year"])
        slow = min(ev, key=lambda k: ev[k]["slope_per_year"])
        return (f"{names[fast].capitalize()} nights: {ev[fast]['slope_per_year']:+.3f} °C a year; "
                f"{names[slow]} nights: {ev[slow]['slope_per_year']:+.3f}.")
    if f["id"] == "unusual-months":
        return f"{ev['count']} cell-months were far outside normal: leads to check, not findings."
    return f["statement"]


def _enrich(f: dict) -> dict:
    return {**f, **DETAILS[f["id"]], **_computed_details(f), "period": PERIOD, "source": SOURCE, "variable": "Nighttime land surface temperature",
            "observation": f["statement"], "confidence": _confidence(f), "evidence_text": _evidence_text(f),
            "sample_size": f.get("evidence", {}).get("tested", len(f.get("cells", [])))}


@lru_cache(maxsize=1)
def _investigate(sha: str) -> dict:
    grid = load_grid()
    findings = [_enrich(f) for f in (h1_widespread(), h2_heterogeneity(), _localized(+1), _localized(-1),
                                     h5_seasons(), h6_anomalies())]
    return tools.finite({
        "engine": "Deterministic AI investigator (hypothesis -> tools -> challenge); no language model at run time",
        "provenance": grid.describe(),
        "rules": ["Observations are read-only; failed-QC months stay missing",
                  "Benjamini-Hochberg FDR whenever many cells or seasons are tested",
                  "'supported' = corrected-significant AND survives the challenge; otherwise 'exploratory'"],
        "caveats": CAVEATS,
        "findings": findings,
    })


_LOCK = threading.Lock()


def investigate() -> dict:
    """Computed once per data file; concurrent callers wait for the same result."""
    with _LOCK:
        return _investigate(load_grid().sha256)


def public_discoveries() -> dict:
    """Only what the public page needs: statements, statuses and cell outlines. No time series."""
    report = investigate()
    keep = ("id", "title", "hypothesis", "status", "statement", "observation", "challenge", "highlight", "cells",
            "location", "period", "source", "variable", "evidence_text", "confidence", "method", "limitations",
            "next_question", "sample_size", "summary")
    return {"engine": report["engine"], "caveats": report["caveats"], "rules": report["rules"],
            "provenance": {k: report["provenance"][k] for k in ("sha256", "data_version", "cells", "months", "period")},
            "findings": [{k: f[k] for k in keep} for f in report["findings"]]}
