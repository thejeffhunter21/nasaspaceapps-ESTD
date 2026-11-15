"""Ask the Climate Detective: answers a visitor's question from the grid-cell analysis tools.

No language model runs here (the AI layer's release rule: the live demo never calls Gemini).
The question is read for places, cells, quarters, years, months and seasons, routed to an
intent, and answered by the same server-side tools the AI investigator uses. Every number in
an answer comes straight from a tool result; nothing is estimated or filled.

Answer shape: headline (one sentence), stats (up to 4 tiles), details (bullets), method,
caveat, cells (for the map), tools_used, suggestions.
"""

from __future__ import annotations

import math
import re
from functools import lru_cache

import pymannkendall as mk

from . import tools
from .grid import QUARTER_REGION, load_grid

ENGINE = ("Climate Detective question engine: reads the question, runs the analysis tools and writes "
          "the answer from their numbers (no language model)")
WHOLE = "phoenix_study_area"
REGION_NAME = {WHOLE: "the whole Phoenix study area", "phoenix_northwest": "the Northwest quarter",
               "phoenix_northeast": "the Northeast quarter", "phoenix_southwest": "the Southwest quarter",
               "phoenix_southeast": "the Southeast quarter"}
QUARTER_NAME = {"NW": "Northwest", "NE": "Northeast", "SW": "Southwest", "SE": "Southeast"}
PLACES = {  # lat, lon (all inside the study window 33.2–33.8 N, 112.4–111.6 W)
    "downtown phoenix": (33.4484, -112.074), "downtown": (33.4484, -112.074), "tempe": (33.4255, -111.94),
    "glendale": (33.5387, -112.186), "scottsdale": (33.4942, -111.926), "mesa": (33.4152, -111.8315),
    "chandler": (33.3062, -111.8413), "gilbert": (33.3528, -111.789), "peoria": (33.5806, -112.2374),
    "sky harbor": (33.4342, -112.0116), "airport": (33.4342, -112.0116), "paradise valley": (33.531, -111.9426),
    "south mountain": (33.335, -112.06), "ahwatukee": (33.33, -111.98), "laveen": (33.363, -112.17),
    "maryvale": (33.50, -112.18), "camelback": (33.515, -111.962), "asu": (33.4242, -111.9281),
    "avondale": (33.4356, -112.3496), "fountain hills": (33.6045, -111.7174), "tolleson": (33.45, -112.259),
}
MONTHS = ["january", "february", "march", "april", "may", "june", "july", "august", "september",
          "october", "november", "december"]
MONTH_ABBR = {m[:3]: i + 1 for i, m in enumerate(MONTHS)}
SEASONS = {"winter": "DJF", "spring": "MAM", "summer": "JJA", "autumn": "SON", "fall": "SON"}
SEASON_WORD = {"DJF": "winter", "MAM": "spring", "JJA": "summer", "SON": "autumn"}
CAVEAT = "Nighttime land surface temperature from NASA MODIS (not air temperature). Describes 2003–2024; not a forecast."
GLOSSARY = [
    (r"land surface temp|\blst\b", "Land surface temperature is how hot the ground, roofs and roads are, measured from space by their infrared glow. At night it shows how much heat the city holds after sunset. It is not the air temperature a weather station reports, though the two are related."),
    (r"modis|mod11|terra|satellite", "MODIS is an instrument on NASA's Terra satellite. Its MOD11C3 product gives a monthly land surface temperature on a 0.05° grid (about 5 km). We use the nighttime value (version 6.1) and keep only months that passed NASA's quality control."),
    (r"heat island", "An urban heat island is a city that stays warmer than its surroundings, especially at night, because pavement and buildings store heat during the day and release it after dark. This project measures nighttime surface warming; on its own it does not prove the cause."),
    (r"mann.?kendall", "The seasonal Mann-Kendall test asks whether values tend to rise (or fall) over the years. It compares each January only with other Januaries, each February with Februaries, and so on, so the normal summer–winter cycle never counts as a trend."),
    (r"sen'?s? ?slope|sen slope", "Sen's slope is the median of the changes between all pairs of observations (within the same calendar month here). It gives a robust warming rate in °C per year that a few unusual months cannot pull around."),
    (r"false discovery|\bfdr\b|benjamini|q.?value", "When 192 cells are tested at once, some would look significant by luck. The Benjamini-Hochberg false discovery rate correction turns each p-value into a q-value; q < 0.05 keeps the expected share of false alarms under 5%."),
    (r"confidence interval|\bci\b|95%", "A 95% confidence interval is the range of warming rates consistent with the data. If it sits entirely above zero, warming is clear; if two intervals overlap a lot, the difference between them may not be real."),
    (r"p.?value", "A p-value is how surprising the data would be if there were no trend at all. Small values (below 0.05) mean a real trend is the better explanation."),
    (r"anomal", "An anomaly is how much a value differs from what is usual. For a month, we compare a cell with its own average for that calendar month over 2003–2024."),
    (r"grid cell|\bcells?\b", "The study window is split into 192 grid cells of 0.05° (about 5 km), 12 rows by 16 columns, grouped into four quarters. Each cell has its own NASA measurement for every month that passed quality control."),
    (r"quality control|\bqc\b|missing", "NASA flags the quality of every pixel. Months that fail are left missing and never filled or estimated; 99.2% of all cell-months are valid."),
    (r"this (project|site|app|website)|how does (this|it) work|what do you do", "This site maps 22 years of NASA nighttime surface temperature over Phoenix, one column per 5 km grid cell. It tests every cell for a warming trend, corrects for testing many cells at once, and lets you ask questions that are answered from those tests."),
]
SUGGEST = ["Is Tempe warming faster than Glendale?", "Which cell warmed the most?", "How hot was July 2024?",
           "Do summer nights warm faster than winter nights?", "What was unusual in 2023?",
           "Which neighbourhoods warm faster than their quarter?"]


# ---------------------------------------------------------------- formatting and data helpers
def _rate(x, d=3) -> str:
    return "—" if x is None else f"{x:+.{d}f} °C/yr"


def _p(p) -> str:
    return "—" if p is None else ("p < 0.001" if p < 0.001 else f"p = {p:.3f}")


def _q(q) -> str:
    return "—" if q is None else ("q < 0.001" if q < 0.001 else f"q = {q:.3f}")


def _cap(s: str) -> str:
    return s[:1].upper() + s[1:]


def _short(label: str) -> str:
    out = label.split(" (")[0]
    return _cap(out[4:]) if out.startswith("the ") else out


@lru_cache(maxsize=2)
def _trend_table(sha: str) -> dict:
    rows = tools.all_cell_trends()["cells"]
    ranked = sorted((r for r in rows if r.get("slope_per_year") is not None), key=lambda r: -r["slope_per_year"])
    return {"rows": {r["id"]: r for r in rows}, "ranked": ranked}


def trends() -> dict:
    return _trend_table(load_grid().sha256)


def period_values(year: int, month: str = "avg") -> dict:
    """Every cell's value and anomaly for one period (exactly what the map shows)."""
    from ..api.explorer import _frame  # local import: the API package imports analysis

    m = "avg" if str(month) in ("avg", "annual", "") else str(int(month))
    if m != "avg" and not 1 <= int(m) <= 12:
        raise tools.ToolError("month must be 1-12 or avg")
    return _frame(load_grid().sha256, int(year), m)


def nearest_cells(lat: float, lon: float, n: int = 3) -> dict:
    grid = load_grid()
    ranked = sorted(grid.cells.values(),
                    key=lambda c: (c.lat - lat) ** 2 + ((c.lon - lon) * math.cos(math.radians(lat))) ** 2)
    return {"point": [lat, lon], "cells": [c.public() for c in ranked[: max(1, min(int(n), 9))]]}


def region_monthly(region_id: str) -> list:
    if region_id not in tools.REGION_IDS:
        raise tools.ToolError(f"unknown region {region_id}")
    return list(tools._regional_series(region_id))


def _years_span() -> int:
    g = load_grid()
    return int(g.months[-1][:4]) - int(g.months[0][:4]) + 1


# ---------------------------------------------------------------- reading the question
def _cell_entity(cid: str, label: str | None = None) -> dict:
    c = load_grid().cells[cid]
    return {"kind": "cell", "id": cid, "label": label or f"cell {cid}", "quarter": c.quarter, "cells": [cid]}


def _region_entity(rid: str) -> dict:
    return {"kind": "region", "id": rid, "label": REGION_NAME[rid], "cells": []}


def _place_label(name: str) -> str:
    return {"asu": "ASU", "airport": "Sky Harbor Airport", "sky harbor": "Sky Harbor Airport"}.get(name, name.title())


def _nm(e: dict) -> str:
    """Name for a sentence: 'the Southeast quarter' for regions, 'Tempe' for places."""
    return e["label"] if e["kind"] == "region" else _short(e["label"])


def parse(question: str, context: dict | None) -> dict:
    q = " " + question.lower().replace("’", "'") + " "
    ctx = context or {}
    grid = load_grid()
    found: list[tuple[int, dict]] = []
    for m in re.finditer(r"\br\d{2}_c\d{2}\b", q):
        if m.group(0) in grid.cells:
            found.append((m.start(), _cell_entity(m.group(0))))
    for name in sorted(PLACES, key=len, reverse=True):
        if name == "downtown" and "downtown phoenix" in q:
            continue
        for m in re.finditer(rf"\b{re.escape(name)}\b", q):
            lat, lon = PLACES[name]
            cid = nearest_cells(lat, lon, 1)["cells"][0]["id"]
            found.append((m.start(), _cell_entity(cid, f"{_place_label(name)} (cell {cid})")))
    quarter_re = {"NW": r"north.?west|\bnw\b", "NE": r"north.?east|\bne\b",
                  "SW": r"south.?west|\bsw\b", "SE": r"south.?east|\bse\b"}
    for qk, pat in quarter_re.items():
        for m in re.finditer(pat, q):
            found.append((m.start(), _region_entity(QUARTER_REGION[qk])))
    for m in re.finditer(r"whole (study )?area|study area|all of phoenix|phoenix overall|\boverall\b|the city|whole city|\bmetro\b", q):
        found.append((m.start(), _region_entity(WHOLE)))
    if re.search(r"this cell|selected cell|that cell|my cell", q) and ctx.get("cell") in grid.cells:
        found.append((q.find("cell"), _cell_entity(ctx["cell"], f"the selected cell {ctx['cell']}")))
    if re.search(r"this (quarter|region)", q) and ctx.get("region") in QUARTER_REGION:
        found.append((q.find("this"), _region_entity(QUARTER_REGION[ctx["region"]])))
    found.sort(key=lambda e: e[0])
    entities, seen = [], set()
    for _, e in found:  # keep question order, drop repeats of the same cell or region
        if (e["kind"], e["id"]) not in seen:
            seen.add((e["kind"], e["id"]))
            entities.append(e)

    first, last = int(grid.months[0][:4]), int(grid.months[-1][:4])
    years_all = [int(y) for y in re.findall(r"\b(19\d\d|20\d\d)\b", q)]
    years = [y for y in years_all if first <= y <= last]
    out_of_range = [y for y in years_all if not first <= y <= last]
    month = None
    for i, name in enumerate(MONTHS):
        if re.search(rf"\b{name}\b", q):
            month = i + 1
    if month is None:
        for ab, i in MONTH_ABBR.items():
            if ab != "may" and re.search(rf"\b{ab}\b", q):
                month = i
    if re.search(r"this month|that month|selected month|this period|on the map", q):
        if str(ctx.get("month", "")) not in ("", "avg", "None"):
            month = int(ctx["month"])
        if not years and ctx.get("year"):
            years = [int(ctx["year"])]
    if re.search(r"this year|that year|selected year", q) and not years and ctx.get("year"):
        years = [int(ctx["year"])]
    seasons = []
    for word, code in SEASONS.items():
        if re.search(rf"\b{word}s?\b", q) and code not in seasons:
            seasons.append(code)
    return {"q": q, "entities": entities, "years": years, "month": month, "seasons": seasons,
            "out_of_range": out_of_range, "range": (first, last), "ctx": ctx}


# ---------------------------------------------------------------- answer pieces
def _answer(headline, stats=(), details=(), method="", cells=(), used=(), kind="answer", caveat=CAVEAT, suggestions=()):
    return {"status": "answered", "kind": kind, "headline": headline, "stats": list(stats)[:4],
            "details": [d for d in details if d], "method": method, "caveat": caveat,
            "cells": list(dict.fromkeys(cells)), "tools_used": list(dict.fromkeys(used)),
            "suggestions": list(suggestions), "engine": ENGINE}


def _stat(label, value, sub=""):
    return {"label": label, "value": value, "sub": sub}


def _series(e: dict) -> list:
    return list(load_grid().cells[e["id"]].values) if e["kind"] == "cell" else region_monthly(e["id"])


def _trend_of(e: dict) -> dict:
    if e["kind"] == "cell":
        t = tools.cell_trend(e["id"])
        row = trends()["rows"].get(e["id"], {})
        rank = next((i + 1 for i, r in enumerate(trends()["ranked"]) if r["id"] == e["id"]), None)
        return {**t, "q": row.get("q"), "significant_fdr": row.get("significant_fdr"), "rank": rank}
    return {**tools.region_stats()["regions"][e["id"]], "rank": None}


def _sig_words(t: dict) -> str:
    if t.get("q") is not None:
        return ("statistically significant after correcting for testing 192 cells" if t.get("significant_fdr")
                else "not significant after correcting for testing 192 cells")
    return "statistically significant" if (t.get("p") or 1) < 0.05 else "not statistically significant"


# ---------------------------------------------------------------- intents
def a_trend(e: dict) -> dict:
    t = _trend_of(e)
    s, span = t["slope_per_year"], _years_span()
    stats = [_stat("Warming rate", _rate(s), "per year, 2003–2024"),
             _stat("95% range", f"{t['ci_low_per_year']:+.3f} to {t['ci_high_per_year']:+.3f}", "°C per year"),
             _stat(f"Over {span} years", f"≈ {s * span:+.1f} °C", "rate × years"),
             _stat("Significance", _q(t["q"]) if t.get("q") is not None else _p(t.get("p")),
                   "corrected for 192 cells" if t.get("q") is not None else "seasonal Mann-Kendall")]
    details = [f"The trend is {_sig_words(t)} ({_p(t.get('p'))}, Kendall's τ = {t['tau']:.2f}), from {t.get('valid_months', '—')} valid months."]
    if t.get("rank"):
        details.append(f"It ranks #{t['rank']} of {len(trends()['ranked'])} cells by warming rate (#1 = fastest).")
        details.append(f"For comparison, the whole study area warms {_rate(tools.region_stats()['regions'][WHOLE]['slope_per_year'])}.")
    else:
        inside = [r for r in trends()["ranked"] if e["id"] == WHOLE or QUARTER_REGION.get(r["quarter"]) == e["id"]]
        if inside:
            details.append(f"Its {len(inside)} cells range from {_rate(inside[-1]['slope_per_year'])} to "
                           f"{_rate(inside[0]['slope_per_year'])}; the fastest is {inside[0]['id']}.")
    word = "warming" if s > 0 else "cooling"
    return _answer(f"{_cap(e['label'])} is {word} at {_rate(s)} at night.", stats, details,
                   "Seasonal Mann-Kendall test and seasonal Sen's slope with a 95% confidence interval"
                   + ("; Benjamini-Hochberg q across 192 cells." if t.get("q") is not None else "."),
                   e["cells"] or ([inside[0]["id"]] if not t.get("rank") and inside else []),
                   ["cell_trend" if e["kind"] == "cell" else "region_stats", "all_cell_trends"])


def a_compare(a: dict, b: dict, q: str = "") -> dict:
    ta, tb = _trend_of(a), _trend_of(b)
    if a["kind"] == b["kind"] == "region":
        d = tools.region_difference(a["id"], b["id"])
        diff, p, lo, hi, n = (d["difference_slope_per_year"], d["p"], d["ci_low_per_year"],
                              d["ci_high_per_year"], d["months_used"])
        used = ["region_stats", "region_difference"]
    else:
        diffs = [x - y if x is not None and y is not None else None for x, y in zip(_series(a), _series(b))]
        t = tools._trend(diffs)
        if t is None:
            raise tools.ToolError("there are not enough months where both have valid data to compare them")
        ci = tools.sen_slope_ci(diffs) or {}
        diff, p, lo, hi, n = (t["slope_per_year"], t["p"], ci.get("ci_low_per_year"), ci.get("ci_high_per_year"),
                              sum(v is not None for v in diffs))
        used = ["cell_trend" if "cell" in (a["kind"], b["kind"]) else "region_stats", "difference_test"]
    sig = p < 0.05
    fast, slow = (a, b) if diff > 0 else (b, a)
    claim_a_faster = bool(re.search(r"(faster|more|quicker|hotter|warmer) than", q))
    claim_a_slower = bool(re.search(r"(slower|less|cooler|colder) than", q))
    lead = ""
    if sig and (claim_a_faster or claim_a_slower):
        lead = "Yes. " if (fast is a) == claim_a_faster else "No. "
    elif not sig and (claim_a_faster or claim_a_slower):
        lead = "Not clearly. "
    head = (f"{lead}{_cap(_nm(fast))} is warming faster than {_nm(slow)}, by {abs(diff):.3f} °C per year."
            if sig else f"{lead}{_cap(_nm(a))} and {_nm(b)} warm at rates that are statistically indistinguishable.")
    stats = [_stat(_short(a["label"]), _rate(ta["slope_per_year"]), f"95%: {ta['ci_low_per_year']:+.3f} to {ta['ci_high_per_year']:+.3f}"),
             _stat(_short(b["label"]), _rate(tb["slope_per_year"]), f"95%: {tb['ci_low_per_year']:+.3f} to {tb['ci_high_per_year']:+.3f}"),
             _stat("Difference", _rate(diff), "" if lo is None else f"95%: {lo:+.3f} to {hi:+.3f}"),
             _stat("Direct test", _p(p), "significant" if sig else "not significant")]
    details = [f"Compared: {a['label']} minus {b['label']}. The test runs on their monthly difference ({n} months where both are valid), so it compares the trends directly instead of comparing two separate p-values; the gap is the trend of that difference.",
               "A difference in warming describes 2003–2024; it is not a cause."]
    return _answer(head, stats, details,
                   "Seasonal Mann-Kendall and Sen's slope on the monthly difference, with a 95% confidence interval.",
                   a["cells"] + b["cells"], used, kind="compare")


def _value_at(e: dict, year: int, month: int | None) -> float | None:
    if e["kind"] == "cell":
        frame = period_values(year, str(month) if month else "avg")
        return next(c["value"] for c in frame["cells"] if c["id"] == e["id"])
    series, months = region_monthly(e["id"]), load_grid().months
    if month:
        return series[months.index(f"{year}-{month:02d}")]
    yr = [x for t, x in zip(months, series) if int(t[:4]) == year]
    return sum(yr) / 12 if len(yr) == 12 and all(x is not None for x in yr) else None


def a_compare_values(a: dict, b: dict, year: int, month: int | None) -> dict:
    when = f"{MONTHS[month - 1].title()} {year}" if month else f"{year} (annual average)"
    va, vb = _value_at(a, year, month), _value_at(b, year, month)
    stats = [_stat(_short(a["label"]), "no valid value" if va is None else f"{va:.1f} °C", when),
             _stat(_short(b["label"]), "no valid value" if vb is None else f"{vb:.1f} °C", when)]
    if va is None or vb is None:
        return _answer(f"Can't compare: {'both have' if va is None and vb is None else 'one of them has'} no valid value for {when} (missing months are never filled).",
                       stats, cells=a["cells"] + b["cells"], used=["period_values"], kind="no_data")
    d = va - vb
    stats.append(_stat("Difference", f"{d:+.1f} °C", f"{_short(a['label'])} minus {_short(b['label'])}"))
    hot, cold = (a, b) if d >= 0 else (b, a)
    head = (f"In {when}, {_nm(hot)} was {abs(d):.1f} °C warmer at night than {_nm(cold)}."
            if round(abs(d), 1) > 0 else f"In {when}, {_nm(a)} and {_nm(b)} measured the same, {va:.1f} °C.")
    return _answer(head, stats, ["One month's difference is a snapshot; ask how fast each is warming for the long-term picture."],
                   "Values read directly from the grid cells or the published regional series.",
                   a["cells"] + b["cells"], ["period_values"], kind="compare")


def a_compare_years(e: dict, y1: int, y2: int, month: int | None) -> dict:
    w1 = f"{MONTHS[month - 1].title()} {y1}" if month else str(y1)
    w2 = f"{MONTHS[month - 1].title()} {y2}" if month else str(y2)
    v1, v2 = _value_at(e, y1, month), _value_at(e, y2, month)
    stats = [_stat(w1, "no valid value" if v1 is None else f"{v1:.1f} °C", "annual average" if not month else ""),
             _stat(w2, "no valid value" if v2 is None else f"{v2:.1f} °C", "annual average" if not month else "")]
    if v1 is None or v2 is None:
        which = " and ".join(w for w, v in ((w1, v1), (w2, v2)) if v is None)
        why = "that month failed NASA quality control" if month else "an annual average needs all 12 months to be valid"
        return _answer(f"Can't compare {w1} and {w2} for {e['label']}: {which} has no valid value ({why}). Missing values are never filled.",
                       stats, cells=e["cells"], used=["region_monthly"], kind="no_data")
    d = v2 - v1
    stats.append(_stat("Change", f"{d:+.1f} °C", f"{w2} minus {w1}"))
    t = _trend_of(e)
    stats.append(_stat("Long-term trend", _rate(t["slope_per_year"]), "all years, for context"))
    return _answer(f"{_cap(e['label'])} was {abs(d):.1f} °C {'warmer' if d > 0 else 'cooler'} at night in {w2} than in {w1} ({v2:.1f} vs {v1:.1f} °C).",
                   stats, ["Two single years can differ by chance; the long-term trend uses every month from 2003 to 2024."],
                   "Values from the grid cell or the published regional series; trend from seasonal Mann-Kendall and Sen's slope.",
                   e["cells"], ["region_monthly", "period_values", "region_stats"], kind="compare")


def a_quarters(p: dict) -> dict:
    low = bool(re.search(r"slowest|least|lowest|coolest", p["q"]))
    st = tools.region_stats()["regions"]
    rows = sorted(((q, st[r]) for q, r in QUARTER_REGION.items()), key=lambda x: x[1]["slope_per_year"], reverse=not low)
    q0, s0 = rows[0]
    return _answer(f"The {QUARTER_NAME[q0]} quarter is warming {'slowest' if low else 'fastest'}, at {_rate(s0['slope_per_year'])}.",
                   [_stat(QUARTER_NAME[q], _rate(s["slope_per_year"]), f"95%: {s['ci_low_per_year']:+.3f} to {s['ci_high_per_year']:+.3f}") for q, s in rows],
                   ["Overlapping 95% ranges mean two quarters may not truly differ; ask e.g. 'compare the southeast and northeast' for a direct test."],
                   "Seasonal Mann-Kendall and Sen's slope on each quarter's published series, with 95% confidence intervals.",
                   [], ["region_stats"], kind="ranking")


def a_place_climate(p: dict) -> dict:
    from ..api.explorer import _baselines

    low = bool(re.search(r"coolest|coldest|lowest", p["q"]))
    base = _baselines(load_grid().sha256)
    rows = sorted(((cid, b["annual"]) for cid, b in base.items() if b["annual"] is not None), key=lambda x: x[1], reverse=not low)
    cells = load_grid().cells
    top = rows[0][0]
    near = min(PLACES, key=lambda k: (PLACES[k][0] - cells[top].lat) ** 2 + (PLACES[k][1] - cells[top].lon) ** 2)
    return _answer(f"The {'coolest' if low else 'warmest'} place at night is cell {top} ({QUARTER_NAME[cells[top].quarter]} quarter, near {_place_label(near)}), averaging {rows[0][1]:.1f} °C.",
                   [_stat(f"#{i + 1}", f"{v:.1f} °C", f"{cid} · {QUARTER_NAME[cells[cid].quarter]}") for i, (cid, v) in enumerate(rows[:4])],
                   [f"Average of each cell's complete-year annual means, 2003–2024 ({len(rows)} cells)."],
                   "Long-term average nighttime land surface temperature per grid cell.", [c for c, _ in rows[:5]],
                   ["period_values"], kind="ranking")


def a_value(e: dict | None, year: int, month: int | None) -> dict:
    frame = period_values(year, str(month) if month else "avg")
    when = f"{MONTHS[month - 1].title()} {year}" if month else f"{year} (annual average)"
    if e is None or (e["kind"] == "region" and e["id"] == WHOLE):
        vals = [c for c in frame["cells"] if c["value"] is not None]
        if not vals:
            return _answer(f"No cell has a valid measurement for {when}.", used=["period_values"], kind="no_data")
        hot, cold = max(vals, key=lambda c: c["value"]), min(vals, key=lambda c: c["value"])
        mean = sum(c["value"] for c in vals) / len(vals)
        anoms = [c["anomaly"] for c in vals if c["anomaly"] is not None]
        mean_anom = sum(anoms) / len(anoms) if anoms else None
        warmer = sum(x > 0 for x in anoms)
        stats = [_stat("Average of cells", f"{mean:.1f} °C", when),
                 _stat("Warmest cell", f"{hot['value']:.1f} °C", hot["id"]),
                 _stat("Coolest cell", f"{cold['value']:.1f} °C", cold["id"]),
                 _stat("vs usual", "—" if mean_anom is None else f"{mean_anom:+.1f} °C", f"{warmer} of {len(anoms)} cells warmer than usual")]
        base = "average for that calendar month" if month else "average of complete years"
        return _answer(f"In {when}, Phoenix nights averaged {mean:.1f} °C at the surface across {len(vals)} cells.", stats,
                       [f"{len(frame['cells']) - len(vals)} cells have no valid value for this period (failed quality control or an incomplete year)." if len(vals) < len(frame["cells"]) else "",
                        f"'vs usual' compares each cell with its own {base}, 2003–2024."],
                       "Values read directly from the NASA MOD11C3 grid cells; anomalies against each cell's own baseline.",
                       [hot["id"], cold["id"]], ["period_values"], kind="value")
    if e["kind"] == "cell":
        c = next(x for x in frame["cells"] if x["id"] == e["id"])
        if c["value"] is None:
            why = "an annual average needs all 12 months" if not month else "that month failed NASA quality control"
            return _answer(f"There is no valid value for {e['label']} in {when}: {why}. It stays missing and is never filled.",
                           [_stat("Valid months that year", f"{c['valid_months_in_year']} of 12")],
                           cells=e["cells"], used=["period_values"], kind="no_data")
        valid = sorted((x["value"] for x in frame["cells"] if x["value"] is not None), reverse=True)
        head = f"{_cap(e['label'])} measured {c['value']:.1f} °C at night in {when}"
        if c["anomaly"] is not None:
            head += f", {abs(c['anomaly']):.1f} °C {'warmer' if c['anomaly'] > 0 else 'cooler'} than usual"
        return _answer(head + ".",
                       [_stat("Surface temperature", f"{c['value']:.1f} °C", when),
                        _stat("vs usual", "—" if c["anomaly"] is None else f"{c['anomaly']:+.1f} °C", "this cell's own baseline"),
                        _stat("Rank that period", f"#{valid.index(c['value']) + 1} of {len(valid)}", "#1 = warmest cell"),
                        _stat("Valid months that year", f"{c['valid_months_in_year']} of 12")],
                       [], "Value read directly from the NASA MOD11C3 grid cell; anomaly against the same cell's 2003–2024 average.",
                       e["cells"], ["period_values"], kind="value")
    series, months = region_monthly(e["id"]), load_grid().months
    usual, same = None, []
    if month:
        v = series[months.index(f"{year}-{month:02d}")]
        same = [x for t, x in zip(months, series) if int(t[5:7]) == month and x is not None]
        usual = sum(same) / len(same) if same else None
    else:
        yr = [x for t, x in zip(months, series) if int(t[:4]) == year]
        v = sum(yr) / 12 if len(yr) == 12 and all(x is not None for x in yr) else None
    if v is None:
        return _answer(f"{_cap(e['label'])} has no valid value for {when}.", used=["region_monthly"], kind="no_data")
    stats = [_stat("Surface temperature", f"{v:.1f} °C", when)]
    if usual is not None:
        stats.append(_stat("vs usual", f"{v - usual:+.1f} °C", f"{MONTHS[month - 1].title()} average {usual:.1f} °C ({len(same)} years)"))
    return _answer(f"{_cap(e['label'])} averaged {v:.1f} °C at night in {when}.", stats, [],
                   "The published regional series (cosine-latitude weighted mean of the region's cells).",
                   [], ["region_monthly"], kind="value")


def a_extremes(p: dict) -> dict:
    q = p["q"]
    low = bool(re.search(r"slowest|least|coolest|coldest|lowest|smallest|minimum", q))
    temp = bool(re.search(r"hottest|warmest|coolest|coldest|highest temp|lowest temp", q)) and not re.search(r"warming|warmed|fastest|slowest|rate|trend", q)
    region = next((e for e in p["entities"] if e["kind"] == "region" and e["id"] != WHOLE), None)
    quarter_of = {cid: c.quarter for cid, c in load_grid().cells.items()}

    def keep(cid):
        return region is None or QUARTER_REGION[quarter_of[cid]] == region["id"]

    where = f" in {region['label']}" if region else ""
    if temp and not p["years"]:
        e = region or _region_entity(WHOLE)
        months = load_grid().months
        pairs = [(t, v) for t, v in zip(months, region_monthly(e["id"]), strict=True) if v is not None]
        if p["month"]:
            pairs = [x for x in pairs if int(x[0][5:]) == p["month"]]
        t, v = (min if low else max)(pairs, key=lambda x: x[1])
        label = f"{MONTHS[int(t[5:]) - 1].title()} {t[:4]}"
        return _answer(f"The {'coldest' if low else 'hottest'} month on record for {e['label']} was {label}, at {v:.1f} °C.",
                       [_stat("Record month", label), _stat("Surface temperature", f"{v:.1f} °C")],
                       [f"Searched {len(pairs)} valid months, 2003–2024."],
                       "The published regional series.", [], ["region_monthly"], kind="ranking")
    if temp:
        year, month = p["years"][0], p["month"]
        frame = period_values(year, str(month) if month else "avg")
        rows = sorted((c for c in frame["cells"] if c["value"] is not None and keep(c["id"])),
                      key=lambda c: c["value"], reverse=not low)
        if not rows:
            return _answer("No cell has a valid value for that period.", used=["period_values"], kind="no_data")
        when = f"{MONTHS[month - 1].title()} {year}" if month else f"{year} (annual average)"
        return _answer(f"The {'coolest' if low else 'warmest'} cell{where} in {when} was {rows[0]['id']}, at {rows[0]['value']:.1f} °C.",
                       [_stat(f"#{i + 1}", f"{c['value']:.1f} °C", c["id"]) for i, c in enumerate(rows[:4])],
                       [f"Ranked {len(rows)} cells with a valid value."], "Values read directly from the grid cells.",
                       [c["id"] for c in rows[:5]], ["period_values"], kind="ranking")
    ranked = [r for r in trends()["ranked"] if keep(r["id"])]
    if low:
        ranked = ranked[::-1]
    top = ranked[0]
    near = min(PLACES, key=lambda k: (PLACES[k][0] - top["lat"]) ** 2 + (PLACES[k][1] - top["lon"]) ** 2)
    return _answer(f"The {'slowest' if low else 'fastest'}-warming cell{where} is {top['id']} ({QUARTER_NAME[top['quarter']]} quarter, near {_place_label(near)}), at {_rate(top['slope_per_year'])}.",
                   [_stat(f"#{i + 1}", _rate(r["slope_per_year"]), f"{r['id']} · {QUARTER_NAME[r['quarter']]}") for i, r in enumerate(ranked[:4])],
                   [f"95% range for {top['id']}: {top['ci_low_per_year']:+.3f} to {top['ci_high_per_year']:+.3f} °C per year; {_q(top.get('q'))}.",
                    f"Ranked {len(ranked)} cells by their 2003–2024 warming rate."],
                   "Seasonal Mann-Kendall and Sen's slope for every cell; Benjamini-Hochberg q.",
                   [r["id"] for r in ranked[:5]], ["all_cell_trends"], kind="ranking")


def a_seasons(e: dict, seasons: list[str]) -> dict:
    codes = seasons if len(seasons) == 1 else ["DJF", "MAM", "JJA", "SON"]
    res = {s: tools.seasonal_trend(e["id"], s) for s in codes}
    if len(res) == 1:
        s, t = next(iter(res.items()))
        return _answer(f"{_cap(SEASON_WORD[s])} nights in {e['label']} are {'warming' if t['slope_per_year'] > 0 else 'cooling'} at {_rate(t['slope_per_year'])}.",
                       [_stat(_cap(t["season_name"]), _rate(t["slope_per_year"])), _stat("Significance", _p(t["p"]), "Mann-Kendall"),
                        _stat("Years used", str(len(t["years_used"])), "complete seasons only")],
                       [], t["method"] + ".", e["cells"], ["seasonal_trend"], kind="seasons")
    fast = max(res, key=lambda k: res[k]["slope_per_year"])
    slow = min(res, key=lambda k: res[k]["slope_per_year"])
    ratio = res[fast]["slope_per_year"] / res[slow]["slope_per_year"] if res[slow]["slope_per_year"] > 0 else None
    return _answer(f"{_cap(SEASON_WORD[fast])} nights warm fastest in {e['label']} ({_rate(res[fast]['slope_per_year'])}); {SEASON_WORD[slow]} nights warm slowest ({_rate(res[slow]['slope_per_year'])}).",
                   [_stat(_cap(SEASON_WORD[s]), _rate(t["slope_per_year"]), _p(t["p"])) for s, t in res.items()],
                   [f"{_cap(SEASON_WORD[fast])} warming is {ratio:.1f}× the {SEASON_WORD[slow]} rate." if ratio else ""],
                   "Mann-Kendall and Sen's slope on yearly seasonal means (complete seasons only).",
                   e["cells"], ["seasonal_trend"], kind="seasons")


def a_unusual(p: dict) -> dict:
    cell = next((e for e in p["entities"] if e["kind"] == "cell"), None)
    res = tools.anomalies(cell["id"] if cell else None, 3.5, 5000)
    rows = [r for r in res["anomalies"]
            if (not p["years"] or int(r["month"][:4]) in p["years"]) and (not p["month"] or int(r["month"][5:]) == p["month"])]
    scope = (cell["label"] if cell else "all cells") + (f" in {', '.join(map(str, p['years']))}" if p["years"] else "") \
        + (f" ({MONTHS[p['month'] - 1].title()})" if p["month"] else "")
    if not rows:
        return _answer(f"Nothing unusual for {scope}: no month sits 3.5 robust standard deviations from its normal.",
                       details=["Unusual months are leads to inspect, not findings."], method=res["method"] + ".",
                       cells=cell["cells"] if cell else [], used=["anomalies"], kind="no_data")
    top = rows[0]
    return _answer(f"{len(rows)} unusual cell-month{'s' if len(rows) != 1 else ''} for {scope}. The most extreme: {top['id']} in {top['month']}, {top['value']:.1f} °C against a usual {top['calendar_month_median']:.1f} °C.",
                   [_stat(r["month"], f"{r['value']:.1f} °C", f"{r['id']} · usual {r['calendar_month_median']:.1f} °C") for r in rows[:4]],
                   ["These are exploratory leads (a sensor issue, a fire, a flood or a real heat event could all cause one), not statistical findings."],
                   res["method"] + "; threshold 3.5.", [r["id"] for r in rows[:6]], ["anomalies"], kind="unusual")


def a_hotspots(p: dict) -> dict:
    res = tools.localized_differences()
    slower = bool(re.search(r"slower|cool|lag|behind", p["q"]))
    rows = [r for r in res["cells"] if r.get("q") is not None and r["q"] < 0.05 and r.get("consistent_in_both_halves")
            and (r["diff_slope_per_year"] < 0) == slower]
    rows.sort(key=lambda r: abs(r["diff_slope_per_year"]), reverse=True)
    word = "slower" if slower else "faster"
    if not rows:
        return _answer(f"No cell warms significantly {word} than its own quarter.", used=["localized_differences"], kind="no_data")
    counts: dict[str, int] = {}
    for r in rows:
        counts[r["quarter"]] = counts.get(r["quarter"], 0) + 1
    return _answer(f"{len(rows)} neighbourhood cells warm significantly {word} than their own quarter. The strongest is {rows[0]['id']}, {_rate(rows[0]['diff_slope_per_year'])} compared with its quarter.",
                   [_stat(r["id"], _rate(r["diff_slope_per_year"]), f"{QUARTER_NAME[r['quarter']]} · {_q(r['q'])}") for r in rows[:4]],
                   ["By quarter: " + ", ".join(f"{QUARTER_NAME[k]} {v}" for k, v in sorted(counts.items(), key=lambda kv: -kv[1])) + ".",
                    "Counted only if significant after correction (q < 0.05) and in the same direction in 2003–2013 and 2014–2024."],
                   res["method"] + ".", [r["id"] for r in rows[:20]], ["localized_differences"], kind="hotspots")


def a_coverage(p: dict) -> dict:
    grid = load_grid()
    total = len(grid.cells) * len(grid.months)
    valid = sum(v is not None for c in grid.cells.values() for v in c.values)
    worst = min(grid.cells.values(), key=lambda c: sum(v is not None for v in c.values))
    stats = [_stat("Valid cell-months", f"{valid:,} of {total:,}", f"{valid / total:.1%}"),
             _stat("Least complete cell", worst.id, f"{sum(v is not None for v in worst.values)} of {len(grid.months)} months")]
    cell = next((e for e in p["entities"] if e["kind"] == "cell"), None)
    if cell:
        c = grid.cells[cell["id"]]
        stats.insert(0, _stat(_short(cell["label"]), f"{sum(v is not None for v in c.values)} of {len(grid.months)}", "valid months"))
    return _answer(f"{valid / total:.1%} of all cell-months passed NASA quality control; the rest stay missing and are never filled.",
                   stats, ["An annual average is shown only when all 12 months of that year are valid."],
                   "Counts of valid values in the grid-cell export.", [worst.id] + (cell["cells"] if cell else []),
                   ["list_cells"], kind="coverage")


def a_background(text: str) -> dict:
    return _answer(text, method="Background explanation (general knowledge, not a result computed from our data).",
                   kind="background", caveat="", suggestions=SUGGEST[:3])


def a_forecast(p: dict) -> dict:
    out = a_trend(p["entities"][0] if p["entities"] else _region_entity(WHOLE))
    out["headline"] = "We don't forecast, but here is the measured past: " + out["headline"][0].lower() + out["headline"][1:]
    out["details"].insert(0, "This project describes what NASA measured from 2003 to 2024; it does not predict the future, and a past trend can change.")
    out["kind"] = "forecast"
    return out


def a_cause(p: dict) -> dict:
    out = a_hotspots({"q": ""})
    out["kind"] = "cause"
    out["headline"] = "Our data shows where and how fast nights warmed, not why."
    out["details"] = ["Background: common explanations for warmer city nights include pavement and roofs storing daytime heat, less vegetation and waste heat. Here these are hypotheses, not results.",
                      "A good next step: compare the cells below (warming faster than their own quarter) with land-cover change since 2003."] + out["details"]
    return out


@lru_cache(maxsize=2)
def _halves_table(sha: str) -> list[dict]:
    out = []
    for cid in load_grid().cells:
        h = tools.cell_trend(cid)["halves"]
        out.append({"id": cid, "halves": [x.get("slope_per_year") for x in h],
                    "gap": any(x.get("status") == "insufficient data" for x in h)})
    return out


def a_halves(p: dict) -> dict:
    rows = _halves_table(load_grid().sha256)
    sig = {r["id"] for r in trends()["ranked"] if r.get("significant_fdr") and r["slope_per_year"] > 0}
    rows = [r for r in rows if r["id"] in sig]
    both = [r for r in rows if all(x is not None and x > 0 for x in r["halves"])]
    gap = [r for r in rows if r["gap"]]
    flat = [r for r in rows if not r["gap"] and r not in both]
    examples = sorted(flat, key=lambda r: min(r["halves"]))[:4]
    return _answer(f"{len(rows) - len(both)} of {len(rows)} warming cells don't warm in both halves of the record: {len(gap)} because one half has too few valid months (a data gap), {len(flat)} because one half shows no warming (a real change in the measurements).",
                   [_stat("Warm in both halves", f"{len(both)} of {len(rows)}", "2003–2013 and 2014–2024"),
                    _stat("Data gap in a half", str(len(gap)), "too few valid months to test"),
                    _stat("Flat or cooling in a half", str(len(flat)), "measured, not a gap")]
                   + ([_stat("Clearest example", examples[0]["id"], f"halves {examples[0]['halves'][0]:+.3f} / {examples[0]['halves'][1]:+.3f} °C/yr")] if examples else []),
                   ["A half needs enough valid months in every calendar month for the seasonal test; missing months are never filled to make it pass.",
                    "Each half is short (11 years), so a flat half can also mean the trend is too small to detect in that window."],
                   "Seasonal Mann-Kendall and Sen's slope re-run separately on 2003–2013 and 2014–2024 for every significantly warming cell.",
                   [r["id"] for r in (examples + gap)[:20]], ["all_cell_trends", "cell_trend"], kind="halves")


def a_cluster(p: dict) -> dict:
    low = bool(re.search(r"slowest|slower|least", p["q"]))
    ranked = trends()["ranked"][::-1] if low else trends()["ranked"]
    top = ranked[:20]
    pos = {r["id"]: (int(r["id"][1:3]), int(r["id"][5:7])) for r in top}
    ids = set(pos)
    touching = [i for i in ids if any(o != i and abs(pos[o][0] - pos[i][0]) <= 1 and abs(pos[o][1] - pos[i][1]) <= 1 for o in ids)]
    groups, seen = [], set()
    for i in ids:  # connected groups of touching cells (8-neighbour)
        if i in seen:
            continue
        stack, grp = [i], []
        while stack:
            k = stack.pop()
            if k in seen:
                continue
            seen.add(k)
            grp.append(k)
            stack += [o for o in ids if o not in seen and abs(pos[o][0] - pos[k][0]) <= 1 and abs(pos[o][1] - pos[k][1]) <= 1]
        groups.append(grp)
    groups.sort(key=len, reverse=True)
    counts: dict[str, int] = {}
    for r in top:
        counts[r["quarter"]] = counts.get(r["quarter"], 0) + 1
    word = "slowest" if low else "fastest"
    return _answer(f"Yes, they cluster: {len(touching)} of the 20 {word}-warming cells touch another one, and the largest group has {len(groups[0])} cells.",
                   [_stat("Touching another top-20 cell", f"{len(touching)} of 20"), _stat("Largest group", f"{len(groups[0])} cells", ", ".join(sorted(groups[0])[:3]) + "…"),
                    _stat("Separate groups", str(len(groups))), _stat("By quarter", ", ".join(f"{k} {v}" for k, v in sorted(counts.items(), key=lambda kv: -kv[1])))],
                   ["Neighbouring cells are spatially correlated, so a cluster is one pattern, not 20 independent discoveries.",
                    "Our data has no land-cover records, so whether they share land-cover change needs an outside dataset (for example the USGS National Land Cover Database)."],
                   "Top 20 cells by seasonal Sen's slope; cells count as touching if they share an edge or corner.",
                   [r["id"] for r in top], ["all_cell_trends"], kind="cluster")


EXTERNAL = [
    (r"urbani[sz]|land.?cover|built|development|construction|population|buildings?|impervious|paved",
     "urbanisation or land-cover change", "local-faster",
     "the National Land Cover Database (USGS) or Landsat impervious-surface maps"),
    (r"\bparks?\b|farm|agricultur|mountain|terrain|vegetation|green|irrigat|desert|elevation",
     "land use or terrain", "local-slower", "the National Land Cover Database (USGS) and a digital elevation model"),
    (r"heat ?waves?|sensor|instrument|fire|flood|weather station|air temperature",
     "heat waves, sensor issues or ground weather records", "unusual", "NOAA station records and MODIS quality flags"),
]


def a_external(topic: str, show: str, source: str, p: dict) -> dict:
    base = a_hotspots({"q": "slower" if show == "local-slower" else ""}) if show.startswith("local") else a_unusual({**p, "years": [], "month": None})
    base["kind"] = "outside_data"
    base["details"] = [f"Our dataset is NASA satellite surface temperature only; it has no records of {topic}, so I can't test that claim.",
                       f"What I can show: the cells below are the place to start. Comparing them with {source} would answer the question.",
                       *base["details"]]
    base["headline"] = f"That needs data on {topic}, which this project doesn't have. Here are the cells to check."
    return base


def a_season_gap(e: dict) -> dict:
    grid = load_grid()
    by = dict(zip(grid.months, _series(e)))
    years, gaps = [], []
    for y in range(int(grid.months[0][:4]), int(grid.months[-1][:4]) + 1):
        jja = [by.get(f"{y}-{m:02d}") for m in (6, 7, 8)]
        djf = [by.get(f"{y - 1}-12"), by.get(f"{y}-01"), by.get(f"{y}-02")]
        if all(v is not None for v in jja + djf):
            years.append(y)
            gaps.append(sum(jja) / 3 - sum(djf) / 3)
    if len(gaps) < 10:
        raise tools.ToolError("too few years with complete summers and winters")
    r = mk.original_test(gaps)
    sig = r.p < 0.05
    return _answer(f"{'Yes' if sig else 'No'}: the summer-minus-winter gap in {e['label']} is {'growing' if r.slope > 0 else 'shrinking'} by {abs(r.slope):.3f} °C per year, which is {'' if sig else 'not '}statistically significant ({_p(r.p)}).",
                   [_stat("Gap trend", _rate(float(r.slope)), "summer minus winter"), _stat("Significance", _p(float(r.p)), "Mann-Kendall"),
                    _stat("Average gap", f"{sum(gaps) / len(gaps):.1f} °C", f"{len(years)} complete years"),
                    _stat("Range", f"{min(gaps):.1f} to {max(gaps):.1f} °C")],
                   ["This tests the difference directly, rather than comparing the summer and winter trends separately."],
                   "Mann-Kendall and Sen's slope on yearly (Jun–Aug mean minus previous Dec–Feb mean); complete seasons only.",
                   e["cells"], ["seasonal_trend"], kind="seasons")


def warm() -> None:
    """Pre-compute the slower tables (called from the API's start-up warm-up thread)."""
    trends()
    _halves_table(load_grid().sha256)


# ---------------------------------------------------------------- entry point
def ask(question: str, context: dict | None = None) -> dict:
    question = (question or "").strip()
    if not question:
        raise tools.ToolError("Ask a question.")
    p = parse(question, context)
    try:
        out = _route(p)
    except tools.ToolError as exc:
        out = _answer(f"I couldn't answer that: {exc}.", kind="error", caveat="", suggestions=SUGGEST)
    if p["out_of_range"]:
        out["details"].insert(0, f"The data covers {p['range'][0]}–{p['range'][1]}; "
                                 f"{', '.join(map(str, p['out_of_range']))} is outside that range.")
    out["question"] = question
    return tools.finite(out)


def _route(p: dict) -> dict:
    q, ents = p["q"], p["entities"]
    asks_meaning = re.search(r"\bwhat (is|are|does)\b|\bwhat's\b|\bexplain\b|\bdefine\b|\bmeaning\b|\bhow does\b|\bwhat do\b", q)
    if asks_meaning and not p["years"] and not ents and not re.search(r"warmest|hottest|fastest|coolest|slowest|unusual", q):
        for pat, text in GLOSSARY:
            if re.search(pat, q):
                return a_background(text)
    if re.search(r"\bwill\b|future|predict|forecast|next (year|decade)|going to|\b20[3-9]\d\b", q):
        return a_forecast(p)
    if re.search(r"\bwhy\b|cause|because|reason|what makes|driving", q):
        return a_cause(p)
    if re.search(r"cluster|together|next to each other|adjacent|clump|grouped|spread out", q):
        return a_cluster(p)
    for pat, topic, show, source in EXTERNAL:
        if re.search(pat, q):
            return a_external(topic, show, source, p)
    if re.search(r"\bhalf\b|halves|2003.?2013|2014.?2024|lose (their|its) warming|first decade|second decade", q):
        return a_halves(p)
    if (re.search(r"summer.{0,12}(minus|-|and|vs\.?|versus).{0,12}winter|gap between summer|summer.winter", q)
            and re.search(r"difference|gap|minus|trend|significant|grow|widen|shrink", q)) and re.search(r"itself|gap|minus|widen|grow|shrink", q):
        return a_season_gap(ents[0] if ents else _region_entity(WHOLE))
    if len(p["seasons"]) >= 2 or re.search(r"which season|each season|by season|\bseasons\b|seasonal", q):
        return a_seasons(ents[0] if ents else _region_entity(WHOLE), [])
    if re.search(r"this cell|selected cell|that cell|my cell", q) and not any(e["kind"] == "cell" for e in ents):
        return {"status": "not_understood", "kind": "help", "engine": ENGINE,
                "headline": "Click a cell on the map first, then ask about \"this cell\".",
                "details": ["Or name one: a place such as Tempe or Mesa, or a cell id such as r10_c03."],
                "stats": [], "cells": [], "tools_used": [], "method": "", "caveat": "", "suggestions": SUGGEST[:3]}
    if len(set(p["years"])) >= 2 and not re.search(r"warming|trend|rate", q):
        y1, y2 = sorted(set(p["years"]))[:2]
        return a_compare_years(ents[0] if ents else _region_entity(WHOLE), y1, y2, p["month"])
    if len(ents) >= 2:
        if p["years"] and not re.search(r"warming|trend|rate|faster|slower", q):
            return a_compare_values(ents[0], ents[1], p["years"][0], p["month"])
        return a_compare(ents[0], ents[1], q)
    if re.search(r"unusual|anomal|extreme|outlier|weird|strange|\bodd\b|abnormal|spike", q):
        return a_unusual(p)
    if re.search(r"neighbou?rhood|hot ?spot|pocket|\blocal\b|than (its|their) (own )?(quarter|region|surround|area|average)", q):
        return a_hotspots(p)
    if re.search(r"\bmost\b|fastest|slowest|\bleast\b|hottest|warmest|coolest|coldest|highest|lowest|biggest|\btop\b|record", q):
        if re.search(r"quarter|region|\bpart\b|\bside\b", q) and not ents:
            return a_quarters(p)
        if (re.search(r"place|spot|neighbou?rhood|where|area|cell", q) and not p["years"] and not p["month"]
                and not re.search(r"warming|warmed|fastest|slowest|rate|trend|month", q)):
            return a_place_climate(p)
        return a_extremes(p)
    if re.search(r"missing|coverage|\bgaps?\b|quality|how many months|valid data", q):
        return a_coverage(p)
    if p["seasons"]:
        return a_seasons(ents[0] if ents else _region_entity(WHOLE), p["seasons"])
    if p["years"]:
        return a_value(ents[0] if ents else None, p["years"][0], p["month"])
    if ents or re.search(r"warm|trend|rate|fast|getting|increas|chang|hotter|cooler|heat|rising|\brise\b|phoenix", q):
        return a_trend(ents[0] if ents else _region_entity(WHOLE))
    if asks_meaning:
        for pat, text in GLOSSARY:
            if re.search(pat, q):
                return a_background(text)
    return {"status": "not_understood", "kind": "help", "engine": ENGINE,
            "headline": "I answer questions about Phoenix's nighttime surface temperature, 2003–2024.",
            "details": ["Name a place (Tempe, Mesa, downtown…), a quarter (Northwest…), a cell id such as r10_c03, a year, a month or a season.",
                        "Ask about warming trends, comparisons, the hottest or fastest-warming cells, unusual months, seasons or data coverage."],
            "stats": [], "cells": [], "tools_used": [], "method": "", "caveat": "", "suggestions": SUGGEST}
