"""Visual layer: page CSS and small HTML blocks. Every supplied string is escaped.

Nothing here computes evidence. Figures arrive from the view model, already labelled.
No web fonts, CDNs or images, so the offline demo looks the same as the live site.
"""

from __future__ import annotations

from html import escape

# Night-sky palette: cool background, heat colours for warming, cool blue for cooling.
INK = "#0A0F1E"
PANEL = "#121A30"
LINE = "rgba(150, 168, 220, 0.16)"
TEXT = "#EAEEF9"
MUTED = "#A3ADCB"
HEAT = "#FF8A3D"
AMBER = "#FFC857"
COOL = "#62B4FF"
SANS = ('ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", '
        'Arial, sans-serif')
SERIF = '"Iowan Old Style", "Palatino Linotype", Palatino, Georgia, "Times New Roman", serif'

CSS = f"""
<style>
:root {{
  --ink: {INK}; --panel: {PANEL}; --line: {LINE}; --text: {TEXT}; --muted: {MUTED};
  --heat: {HEAT}; --amber: {AMBER}; --cool: {COOL};
}}
html, body, [data-testid="stApp"] {{ font-family: {SANS}; }}
[data-testid="stApp"] {{
  background:
    radial-gradient(1200px 500px at 85% -10%, rgba(255, 138, 61, 0.13), transparent 60%),
    radial-gradient(900px 500px at -10% 10%, rgba(98, 180, 255, 0.10), transparent 60%),
    var(--ink);
}}
[data-testid="stHeader"] {{ background: transparent; }}
[data-testid="stMainBlockContainer"] {{ max-width: 1180px; padding-top: 2.2rem; }}
h1, h2, h3, [data-testid="stHeading"] h3 {{ font-family: {SERIF} !important;
  letter-spacing: -0.01em; }}
[data-testid="stHeading"] h3 {{ font-size: clamp(1.7rem, 3vw, 2.3rem); color: var(--text); }}
[data-testid="stCaptionContainer"] {{ color: var(--muted); }}
a {{ color: var(--amber); }}
:focus-visible {{ outline: 3px solid var(--amber) !important; outline-offset: 2px; }}

/* Hero */
.estd-hero {{ position: relative; padding: 2.4rem 2.2rem 2rem; border-radius: 24px;
  border: 1px solid var(--line); overflow: hidden;
  background: linear-gradient(135deg, rgba(18, 26, 48, 0.95), rgba(10, 15, 30, 0.85)); }}
.estd-hero::after {{ content: ""; position: absolute; inset: 0; pointer-events: none;
  background-image:
    radial-gradient(1.2px 1.2px at 12% 22%, rgba(255,255,255,.55), transparent 60%),
    radial-gradient(1px 1px at 32% 68%, rgba(255,255,255,.35), transparent 60%),
    radial-gradient(1.4px 1.4px at 58% 18%, rgba(255,255,255,.5), transparent 60%),
    radial-gradient(1px 1px at 74% 54%, rgba(255,255,255,.3), transparent 60%),
    radial-gradient(1.2px 1.2px at 90% 30%, rgba(255,255,255,.45), transparent 60%),
    radial-gradient(1px 1px at 46% 86%, rgba(255,255,255,.3), transparent 60%); }}
.estd-hero .glow {{ position: absolute; right: -120px; bottom: -160px; width: 420px;
  height: 420px; border-radius: 50%; filter: blur(10px); pointer-events: none;
  background: radial-gradient(circle, rgba(255,138,61,.45), rgba(255,200,87,.12) 45%,
  transparent 70%); }}
.estd-eyebrow {{ font-size: .78rem; font-weight: 700; letter-spacing: .16em;
  text-transform: uppercase; color: var(--amber); margin: 0 0 .8rem; }}
.estd-hero h1 {{ font-size: clamp(2rem, 4.6vw, 3.4rem); line-height: 1.05; margin: 0;
  padding: 0; color: var(--text); font-weight: 700; max-width: 16ch; }}
.estd-hero h1 em {{ font-style: italic; color: var(--heat); }}
.estd-hero p.lede {{ font-size: 1.08rem; line-height: 1.55; color: var(--muted);
  max-width: 60ch; margin: 1rem 0 1.3rem; }}
.estd-chips {{ display: flex; flex-wrap: wrap; gap: .5rem; position: relative; z-index: 1; }}
.estd-chip {{ font-size: .8rem; color: var(--text); padding: .35rem .75rem;
  border-radius: 999px; border: 1px solid var(--line); background: rgba(255,255,255,.04); }}

/* Section labels */
.estd-section {{ margin: 2.4rem 0 .6rem; }}
.estd-section .kicker {{ font-size: .74rem; font-weight: 700; letter-spacing: .14em;
  text-transform: uppercase; color: var(--amber); }}
.estd-section h3 {{ margin: .25rem 0 .3rem; font-size: 1.55rem; color: var(--text); }}
.estd-section p {{ margin: 0; color: var(--muted); max-width: 72ch; line-height: 1.5; }}

.estd-note {{ color: var(--muted); max-width: 72ch; line-height: 1.5; margin: 0 0 .4rem; }}
.st-key-chart_view label p {{ font-weight: 600; }}

/* Verdict */
.estd-verdict {{ display: flex; gap: 1.1rem; align-items: center; padding: 1.2rem 1.4rem;
  border-radius: 18px; border: 1px solid var(--line); margin: .6rem 0 1rem;
  background: linear-gradient(90deg, rgba(255,138,61,.16), rgba(18,26,48,.6)); }}
.estd-verdict.cool {{ background: linear-gradient(90deg, rgba(98,180,255,.16), rgba(18,26,48,.6)); }}
.estd-verdict.flat {{ background: linear-gradient(90deg, rgba(163,173,203,.14), rgba(18,26,48,.6)); }}
.estd-verdict.sample {{ background: linear-gradient(90deg, rgba(255,200,87,.14), rgba(18,26,48,.6)); }}
.estd-verdict .badge {{ flex: 0 0 auto; width: 3.1rem; height: 3.1rem; border-radius: 14px;
  display: grid; place-items: center; font-size: 1.5rem; font-weight: 800;
  background: rgba(255,138,61,.22); color: var(--heat); }}
.estd-verdict.cool .badge {{ background: rgba(98,180,255,.2); color: var(--cool); }}
.estd-verdict.flat .badge, .estd-verdict.sample .badge {{ background: rgba(163,173,203,.18);
  color: var(--text); }}
.estd-verdict .headline {{ font-family: {SERIF}; font-size: 1.35rem; color: var(--text);
  font-weight: 700; line-height: 1.2; }}
.estd-verdict .sub {{ color: var(--muted); margin-top: .2rem; font-size: .95rem; }}

/* Native metric cards */
[data-testid="stMetric"] {{ background: rgba(18, 26, 48, 0.75); border-radius: 18px;
  padding: 1rem 1.2rem; }}
[data-testid="stMetricLabel"] p {{ font-size: .82rem; letter-spacing: .06em;
  text-transform: uppercase; color: var(--muted); }}
[data-testid="stMetricValue"] {{ font-variant-numeric: tabular-nums; font-weight: 700; }}

/* "What it means" tiles */
.estd-facts {{ display: grid; gap: .8rem; margin: 1rem 0 .4rem;
  grid-template-columns: repeat(auto-fit, minmax(210px, 1fr)); }}
.estd-fact {{ border-radius: 16px; border: 1px solid var(--line); padding: 1rem 1.1rem;
  background: rgba(18, 26, 48, 0.55); }}
.estd-fact .big {{ font-size: 1.7rem; font-weight: 800; color: var(--text);
  font-variant-numeric: tabular-nums; letter-spacing: -0.01em; }}
.estd-fact .big.heat {{ color: var(--heat); }}
.estd-fact .big.cool {{ color: var(--cool); }}
.estd-fact .what {{ color: var(--text); margin-top: .15rem; font-weight: 600; }}
.estd-fact .how {{ color: var(--muted); font-size: .82rem; margin-top: .35rem; line-height: 1.4; }}

/* Charts and panels */
[data-testid="stPlotlyChart"] {{ background: rgba(18, 26, 48, 0.55); border-radius: 18px;
  border: 1px solid var(--line); padding: .4rem .4rem 0; }}
[data-testid="stExpander"] details {{ border-radius: 16px; border: 1px solid var(--line);
  background: rgba(18, 26, 48, 0.55); }}
.st-key-explanation {{ border-radius: 18px; border: 1px solid var(--line);
  padding: 1.1rem 1.3rem; background: linear-gradient(180deg, rgba(255,200,87,.07),
  rgba(18,26,48,.6)); }}
.st-key-explanation [data-testid="stText"], .st-key-explanation pre {{ font-family: {SANS};
  font-size: 1.05rem; line-height: 1.6; color: var(--text); white-space: pre-wrap; }}
.st-key-controls {{ border-radius: 18px; border: 1px solid var(--line);
  padding: .9rem 1.1rem .5rem; background: rgba(18, 26, 48, 0.6); margin-top: 1.2rem; }}

.st-key-mapwrap {{ border-radius: 22px; overflow: hidden; border: 1px solid var(--line);
  box-shadow: 0 30px 80px rgba(0,0,0,.45), 0 0 0 1px rgba(255,200,87,.06) inset;
  background: radial-gradient(800px 400px at 50% 40%, #111a33, #070b16); }}

/* Quarter map */
.estd-map {{ display: grid; grid-template-columns: 1fr 1fr; gap: 6px; padding: 6px;
  border-radius: 20px; border: 1px solid var(--line); background: rgba(10,15,30,.6);
  aspect-ratio: 1 / 1; max-width: 420px; margin: 0 auto; position: relative; }}
.estd-tile {{ border-radius: 14px; padding: .8rem; display: flex; flex-direction: column;
  justify-content: space-between; border: 2px solid transparent; }}
.estd-tile.on {{ border-color: var(--amber); box-shadow: 0 0 0 4px rgba(255,200,87,.18); }}
.estd-tile .q {{ font-size: .72rem; font-weight: 800; letter-spacing: .14em;
  color: rgba(255,255,255,.85); text-transform: uppercase; }}
.estd-tile .v {{ font-size: 1.25rem; font-weight: 800; color: #fff;
  font-variant-numeric: tabular-nums; }}
.estd-tile .s {{ font-size: .74rem; color: rgba(255,255,255,.85); }}
.estd-compass {{ text-align: center; color: var(--muted); font-size: .8rem; margin: .5rem 0 0; }}

/* Limits */
.estd-limits {{ display: grid; gap: .8rem; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); }}
.estd-limit {{ border-radius: 16px; padding: 1rem 1.1rem; border: 1px solid var(--line);
  background: rgba(18,26,48,.5); }}
.estd-limit b {{ color: var(--text); display: block; margin-bottom: .25rem; }}
.estd-limit span {{ color: var(--muted); font-size: .92rem; line-height: 1.45; }}

.estd-footer {{ margin: 3rem 0 1rem; padding-top: 1.2rem; border-top: 1px solid var(--line);
  color: var(--muted); font-size: .85rem; line-height: 1.6; }}

@media (max-width: 640px) {{
  .estd-hero {{ padding: 1.6rem 1.2rem 1.4rem; border-radius: 18px; }}
  .estd-verdict {{ padding: 1rem; }}
  .estd-fact .big {{ font-size: 1.45rem; }}
}}
</style>
"""


def hero_html() -> str:
    return """
<section class="estd-hero" aria-label="Project introduction">
  <div class="glow"></div>
  <p class="estd-eyebrow">NASA Space Apps 2026 &middot; Earth System Trend Detective</p>
  <h1>Are Phoenix nights getting <em>warmer</em>?</h1>
  <p class="lede">We tested every month of NASA satellite measurements of nighttime land
  surface temperature over Phoenix, Arizona, from 2003 to 2024, and asked one question:
  is there a real, statistically significant trend, or just noise?</p>
  <div class="estd-chips">
    <span class="estd-chip">NASA Terra MODIS &middot; MOD11C3 v061</span>
    <span class="estd-chip">Monthly, 2003&ndash;2024</span>
    <span class="estd-chip">Seasonal Mann-Kendall test</span>
    <span class="estd-chip">Significant when p &lt; 0.05</span>
  </div>
</section>
"""


def section_html(kicker: str, title: str, text: str = "") -> str:
    heading = f"<h3>{escape(title)}</h3>" if title else ""
    body = f"<p>{escape(text)}</p>" if text else ""
    return (f'<div class="estd-section"><div class="kicker">{escape(kicker)}</div>'
            f"{heading}{body}</div>")


def note_html(text: str) -> str:
    return f'<p class="estd-note">{escape(text)}</p>'


def verdict_html(view) -> str:
    """Plain-language reading of the supplied direction and significance (p < 0.05)."""
    if view.is_sample:
        tone, mark = "sample", "?"
        headline = "Sample preview: these are not NASA observations"
        sub = "Synthetic numbers for checking the layout. Connect the API for real results."
    elif view.significant and view.direction == "increasing":
        tone, mark = "", "&uarr;"
        headline = "Getting warmer, and the trend is statistically significant"
        sub = f"{escape(view.display_p)} with the {escape(_method_name(view.method))}."
    elif view.significant and view.direction == "decreasing":
        tone, mark = "cool", "&darr;"
        headline = "Getting cooler, and the trend is statistically significant"
        sub = f"{escape(view.display_p)} with the {escape(_method_name(view.method))}."
    else:
        tone, mark = "flat", "&asymp;"
        headline = "No statistically significant trend detected"
        sub = ("p &ge; 0.05: not enough evidence of a trend over this period. "
               "That is not proof of no change.")
    return (f'<div class="estd-verdict {tone}" role="status"><div class="badge" aria-hidden="true">'
            f'{mark}</div><div><div class="headline">{headline}</div>'
            f'<div class="sub">{sub}</div></div></div>')


def _method_name(method: str) -> str:
    return method.split(" with ")[0].split(" (")[0] or method


def _signed(value: float, digits: int) -> str:
    text = f"{value:+.{digits}f}"
    return "0" + text[2:] if text.startswith(("+0.", "-0.")) and float(text) == 0 else text


def facts_html(view) -> str:
    """'What it means' tiles. Each derived figure says exactly how it was made."""
    unit = escape(view.display_units)
    tone = "heat" if view.slope > 0 else "cool" if view.slope < 0 else ""
    per_month_unit = escape(view.display_slope_unit)
    years = escape(view.years_label)
    missing = view.months_total - view.months_observed
    gap_text = ("No missing months." if not missing else
                (f"{missing} missing months left as gaps, never filled in." if missing != 1
                else "1 missing month left as a gap, never filled in."))
    tiles = [
        (f"{_signed(view.per_year_slope, 3)} {unit}", tone, "per year",
         f"The supplied slope ({escape(view.display_slope)} {per_month_unit}) &times; 12."),
        (f"&asymp; {_signed(view.period_change_estimate, 1)} {unit}", tone,
         f"across about {years} years",
         (f"Slope &times; {view.months_total} months. An estimate from the trend line, "
         "not a measured difference between two years.")),
        (f"&tau; = {view.tau:.2f}", "", "trend consistency",
         "Kendall's tau, from &minus;1 to +1: how consistently values rise (+) or fall (&minus;) over time."),
        (f"{view.months_observed}/{view.months_total}", "", "months observed", escape(gap_text)),
    ]
    cells = "".join(
        f'<div class="estd-fact"><div class="big {cls}">{big}</div>'
        f'<div class="what">{what}</div><div class="how">{how}</div></div>'
        for big, cls, what, how in tiles
    )
    return f'<div class="estd-facts">{cells}</div>'


QUARTERS = (("northwest", "NW"), ("northeast", "NE"), ("southwest", "SW"), ("southeast", "SE"))


def quarter_ids(trends: dict) -> dict[str, str] | None:
    """Map NW/NE/SW/SE to region ids when all four quarter boxes were supplied."""
    found = {}
    for suffix, short in QUARTERS:
        matches = [rid for rid in trends if rid.endswith("_" + suffix)]
        if len(matches) != 1:
            return None
        found[short] = matches[0]
    return found


def quarter_map_html(trends: dict, selected_id: str) -> str | None:
    """Four study-area quarters in their real arrangement, shaded by supplied slope."""
    ids = quarter_ids(trends)
    if not ids:
        return None
    slopes = [trends[rid]["slope"] for rid in ids.values()]
    top = max(abs(s) for s in slopes) or 1.0
    tiles = []
    for short, rid in ids.items():
        t = trends[rid]
        strength = 0.25 + 0.65 * abs(t["slope"]) / top
        rgb = "255, 138, 61" if t["slope"] > 0 else "98, 180, 255" if t["slope"] < 0 else "163, 173, 203"
        sig = "significant" if t["p"] < 0.05 else "not significant"
        unit = escape(t["slope_unit"].replace("degC", "°C"))
        on = " on" if rid == selected_id else ""
        tiles.append(
            f'<div class="estd-tile{on}" style="background: rgba({rgb}, {strength:.2f})" '
            f'aria-label="{escape(t["region"])}: slope {t["slope"]:.4g} {unit}, {sig}">'
            f'<div class="q">{short}</div><div><div class="v">{t["slope"] * 12:+.3f}</div>'
            f'<div class="s">°C per year (slope &times; 12) &middot; {sig}</div></div></div>'
        )
    return ('<div class="estd-map" role="img" aria-label="Trend by quarter of the Phoenix study '
            f'area">{"".join(tiles)}</div><p class="estd-compass">North is up. Each tile is one '
            "quarter box of the study area; brighter means a steeper supplied trend.</p>")


def limits_html(view) -> str:
    items = [
        ("Satellite surface, not air", ("Land surface temperature is how warm the ground and "
         "rooftops are, seen from orbit. It is not the air temperature a weather station "
         "or a person measures.")),
        ("Nighttime only", ("These are nighttime overpasses. Daytime heat is a different "
         "measurement and is not shown here.")),
        ("Not a cause", ("The test shows that a trend exists, not why. Urban growth and climate "
         "change are possible reasons that scientists study; we do not prove either.")),
        ("Not a forecast", ("The slope describes the past period. It does not predict next "
         "month or any future year.")),
    ]
    cells = "".join(f'<div class="estd-limit"><b>{escape(title)}</b><span>{escape(text)}</span></div>'
                    for title, text in items)
    return f'<div class="estd-limits">{cells}</div>'


def footer_html() -> str:
    return ("<div class=\"estd-footer\">Data: NASA LP DAAC, Terra MODIS Land Surface Temperature "
            "MOD11C3 v061 (doi:10.5067/MODIS/MOD11C3.061). Statistics: seasonal Mann-Kendall test "
            "with Sen's slope. Built by the Earth System Trend Detective team for NASA Space Apps "
            "2026. Explanation labels show whether text is an automatic summary or AI-assisted.</div>")
