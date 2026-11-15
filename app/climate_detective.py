"""Offline guided investigations over the committed, validated NASA results."""

import json
import re
from pathlib import Path

import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from earth_system_trend.ai.trend import METHODS, TrendInputError, run_trend
from earth_system_trend.contract import Results

ROOT = Path(__file__).resolve().parents[1]
QUESTIONS = (
    "Which region of Phoenix warmed fastest?",
    "Compare nighttime warming in Northeast and Southwest Phoenix.",
    "Has nighttime temperature in Phoenix increased significantly since 2003?",
    "Has nighttime warming accelerated in Phoenix since 2014?",
)
LIMITATION = (
    "These are historical nighttime land surface temperatures, not air temperatures or forecasts. "
    "The observations do not establish causes. Seasonal test p-values assume independence; "
    "temporal dependence can affect significance."
)
UNSUPPORTED = (
    "This demonstration currently supports regional warming comparisons, historical trend "
    "analysis, and selected hypothesis investigations. Try one of the suggested questions. "
    "It uses the fixed Phoenix study window, 2003–2024; hottest and fastest warming are different questions."
)


def interpret_question(question):
    """Conservative predefined patterns; no model or arbitrary tool execution."""
    q = question.lower().strip()
    # Reject unsupported places, periods, variables, and mixed/unknown requests.
    words = set(re.findall(r"[a-z]+", q))
    allowed = {"which", "region", "of", "phoenix", "warmed", "fastest", "compare", "nighttime", "warming", "in", "northeast", "and", "southwest", "has", "temperature", "increased", "significantly", "since", "accelerated", "the", "is", "getting", "warmer", "most", "area", "experienced", "been", "statistically", "significant", "trend", "show", "me", "please", "northwest", "southeast", "vs", "versus", "did", "does", "have", "a", "an", "it", "across", "all", "regions", "how", "much", "evidence", "for", "acceleration", "there", "can", "you", "tell", "whether", "surface", "land", "study", "window", "rate", "rates", "than", "faster", "over", "from", "to", "between", "through"}
    if not words <= allowed:
        return None
    years = re.findall(r"\b\d{4}\b", q)
    if "accelerat" in q:
        if years and years != ["2014"]:
            return None
        if any(c in q for c in ("northeast", "northwest", "southeast", "southwest")):
            return None
        return "test_hypothesis"
    if years and years not in (["2003"], ["2003", "2024"]):
        return None
    regions = [c for c in ("northeast", "northwest", "southeast", "southwest") if c in q]
    if "compare" in q or " vs " in q or "versus" in q:
        return "compare_regions" if set(regions) == {"northeast", "southwest"} else None
    if regions:
        return None
    if any(w in q for w in ("fastest", "warmed most", "most nighttime warming")):
        return "rank_regions"
    if any(w in q for w in ("significan", "warmer", "warming", "trend", "increased")):
        return "describe_trend"
    return None


def load_investigation_data():
    paths = [ROOT / "results/results.json", *sorted((ROOT / "results/regions").glob("*.json"))]
    records = [Results.model_validate(json.loads(p.read_text())).model_dump() for p in paths]
    expected = {"phoenix_study_area", *(f"phoenix_{r}" for r in (
        "northeast", "northwest", "southeast", "southwest"))}
    if {r["region_id"] for r in records} != expected:
        raise ValueError("The committed Phoenix results are incomplete.")
    if any("MOD11C3" not in r["source"] or r["method"] != METHODS["seasonal"] for r in records):
        raise ValueError("Expected approved MOD11C3 seasonal results.")
    return {r["region_id"]: r for r in records}


def evidence_row(r):
    return {"Region": r["region"], "Period": f"{r['period']['start']} – {r['period']['end']}",
            "Slope (°C/year)": r["trend"]["slope"] * 12,
            "p-value": r["trend"]["p"], "Direction": r["trend"]["trend"],
            "Valid months": sum(p["value"] is not None for p in r["series"]),
            "Missing months": sum(p["value"] is None for p in r["series"])}


def add_series(fig, r, points=None, **kwargs):
    points = r["series"] if points is None else points
    fig.add_trace(go.Scatter(x=[p["time"] for p in points], y=[p["value"] for p in points],
                             name=r["region"], mode="lines", connectgaps=False), **kwargs)


def investigate(intent, records):
    main = records["phoenix_study_area"]
    rows = []
    if intent == "rank_regions":
        selected = sorted((r for k, r in records.items() if k != "phoenix_study_area"),
                          key=lambda r: r["trend"]["slope"], reverse=True)
        rows = [evidence_row(r) for r in selected]
        fig = go.Figure(go.Bar(x=[r["region"].replace("Phoenix study area ", "").title()
                                 for r in selected],
                              y=[r["trend"]["slope"] * 12 for r in selected],
                              marker_color=["#f59e0b", "#38bdf8", "#38bdf8", "#38bdf8"]))
        fig.update_layout(yaxis_title="Estimated warming rate (°C/year)", xaxis_title="Phoenix subregion")
        title = "Regional nighttime warming rates · 2003–2024"
        finding = (f"{selected[0]['region']} has the highest estimated warming rate "
                   f"({selected[0]['trend']['slope'] * 12:.3g} °C/year). "
                   "Ranking estimates does not establish statistically significant differences between regions.")
    elif intent == "compare_regions":
        selected = [records[f"phoenix_{r}"] for r in ("northeast", "southwest")]
        fig = go.Figure()
        for r in selected:
            add_series(fig, r)
            rows.append(evidence_row(r))
        title = "Northeast and Southwest Phoenix · 2003–2024"
        finding = (f"Estimated rates: Northeast {selected[0]['trend']['slope'] * 12:.3g} °C/year; "
                   f"Southwest {selected[1]['trend']['slope'] * 12:.3g} °C/year. "
                   "A statistical test of the difference has not been performed; the difference is descriptive.")
    elif intent == "test_hypothesis":
        fig = make_subplots(rows=1, cols=2, subplot_titles=("2003–2013", "2014–2024"),
                            shared_yaxes=True)
        for col, (start, end) in enumerate((("2003-01", "2013-12"), ("2014-01", "2024-12")), 1):
            points = [p for p in main["series"] if start <= p["time"] <= end]
            add_series(fig, main, points, row=1, col=col)
            # Both periods start in January; preserve every calendar position, including gaps.
            try:
                trend = run_trend([p["value"] for p in points], method="seasonal")
                rows.append(evidence_row({**main, "period": {"start": start, "end": end},
                                          "series": points, "trend": trend}))
            except TrendInputError:
                rows.append({"Region": main["region"], "Period": f"{start} – {end}",
                             "Status": "Insufficient coverage for seasonal trend"})
        fig.update_layout(showlegend=False)
        title = "Evidence Challenger · Phoenix nighttime temperatures · 2003–2024"
        finding = ("Verdict: Inconclusive — additional statistical testing required. "
                   "The two period estimates are descriptive. Comparing slopes or separate p-values "
                   "does not prove acceleration. No slope-change test or uncertainty interval is implemented.")
    else:
        fig = go.Figure()
        add_series(fig, main)
        rows = [evidence_row(main)]
        significant = main["trend"]["p"] < 0.05
        finding = (f"Phoenix's estimated nighttime surface temperature trend is "
                   f"{main['trend']['slope'] * 12:.3g} °C/year "
                   f"(p = {main['trend']['p']:.3g}). "
                   + ("The seasonal test supports a historical warming trend at p < 0.05."
                      if significant and main["trend"]["slope"] > 0 else
                      "This test does not establish significant warming; this is not proof of no change."))
        title = "Phoenix nighttime land surface temperature · 2003–2024"
    if intent != "rank_regions":
        fig.update_xaxes(title_text="Observation month")
        fig.update_yaxes(title_text="Nighttime land surface temperature (°C)")
    fig.update_layout(title=title, template="plotly_dark", height=430, margin={"b": 100},
                      legend={"orientation": "h", "y": -0.25})
    fig.add_annotation(text="NASA MOD11C3.061 · phoenix-qc-v1.0 · Seasonal MK / Sen's slope",
                       xref="paper", yref="paper", x=0, y=-0.25, showarrow=False, font_size=10)
    return fig, finding, rows


def render_climate_detective():
    st.markdown("## AI Climate Detective")
    st.caption("Ask questions. Investigate climate trends. Explore the evidence.")
    st.markdown("Turn your climate questions into evidence-backed investigations.")
    st.caption("Guided Investigation Demo · Predefined workflows and locally available results. "
               "No Gemini reasoning is used. Explanations are deterministic.")
    labels = ("Which region warmed fastest?", "Compare Northeast vs. Southwest",
              "Is Phoenix warming significantly?", "Has warming accelerated?")
    for col, label, question in zip(st.columns(4), labels, QUESTIONS, strict=True):
        if col.button(label, key=f"detective_{label}"):
            st.session_state.detective_question = question
    question = st.text_input("Research question", key="detective_question",
                             placeholder=QUESTIONS[0])
    # Results render only for the question explicitly submitted in this run.
    if not st.button("Investigate", type="primary", key="detective_submit"):
        return
    intent = interpret_question(question)
    if intent is None:
        st.info(UNSUPPORTED)
        return
    try:
        with st.status("Following the guided investigation workflow…", expanded=True) as status:
            st.write("✓ Matched question to a predefined investigation")
            records = load_investigation_data()
            st.write("✓ Loaded validated local NASA-derived observations")
            fig, finding, rows = investigate(intent, records)
            st.write("✓ Examined seasonal trend evidence and prepared visualization")
            status.update(label="Investigation ready", state="complete", expanded=False)
        st.markdown(f"**Research question:** {question}")
        st.plotly_chart(fig, width="stretch", key="detective_chart")
        st.markdown("**Key finding**")
        st.info(finding)
        st.markdown("**Scientific evidence**")
        st.dataframe(rows, hide_index=True, width="stretch")
        with st.expander("How was this calculated? · Methodology and source"):
            st.write("Question selection uses predefined keyword patterns. Ranking and comparison use "
                     "stored seasonal Mann–Kendall results and seasonal Sen's slopes (monthly slope × 12 "
                     "for °C/year). Evidence Challenger recomputes the same validated seasonal method "
                     "on the two January-aligned periods, retaining missing positions. It does not test acceleration.")
            st.write(records["phoenix_study_area"]["source"])
            st.markdown("[NASA dataset DOI](https://doi.org/10.5067/MODIS/MOD11C3.061)")
            st.caption("Missing observations stay as chart gaps. No observations are fabricated or imputed.")
        st.caption(LIMITATION)
    except (OSError, ValueError, KeyError):
        st.warning("The guided investigation could not load its local evidence. "
                   "The existing dashboard remains available; restore the committed results files and retry.")
