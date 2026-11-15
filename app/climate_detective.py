"""Guided scientific investigations using approved, local Phoenix observations."""

import json
import re
from pathlib import Path

import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from earth_system_trend.ai.trend import METHODS, TrendInputError, run_trend
from earth_system_trend.contract import Results

ROOT = Path(__file__).resolve().parents[1]
QUESTIONS = {
    "Which region warmed fastest?": "Which region of Phoenix warmed fastest?",
    "Compare Northeast vs. Southwest": "Compare Northeast and Southwest Phoenix.",
    "Is Phoenix warming significantly?": "Has Phoenix warmed significantly since 2003?",
    "Has warming accelerated?": "Has Phoenix warming accelerated since 2014?",
}
LIMITS = (
    "Nighttime land surface temperature is not air temperature. These historical observations "
    "are not forecasts and do not establish causes. Seasonal test p-values assume independence; "
    "temporal dependence can affect significance. Ranking slopes does not test their differences."
)


def interpret_question(question):
    """Recognize a bounded vocabulary; unsupported scope never defaults to Phoenix."""
    q = question.lower().strip()
    vocabulary = (
        "which region regions area of phoenix has have did does the a an experienced "
        "nighttime land surface temperature warming warmed fastest most compare northeast "
        "southwest northwest southeast and vs versus is getting warmer increased "
        "significantly statistically significant since from to between through "
        "accelerated acceleration trend trends show me please evidence for"
    )
    if not set(re.findall(r"[a-z]+", q)) <= set(vocabulary.split()):
        return None
    years = re.findall(r"\b\d+\b", q)
    compass = [r for r in ("northeast", "southwest", "northwest", "southeast") if r in q]
    if "accelerat" in q:
        return "acceleration" if not compass and years in ([], ["2014"]) else None
    if years not in ([], ["2003"], ["2003", "2024"]):
        return None
    if "compare" in q or " vs " in q or "versus" in q:
        return "compare" if set(compass) == {"northeast", "southwest"} else None
    if compass:
        return None
    if "fastest" in q or "warmed most" in q or "most nighttime warming" in q:
        return "rank"
    if any(word in q for word in ("significan", "warmer", "warming", "trend", "increased")):
        return "trend"
    return None


def load_evidence():
    """Use fixed paths only; no user-supplied paths, network requests, or synthetic fallback."""
    paths = [ROOT / "results/results.json", *sorted((ROOT / "results/regions").glob("*.json"))]
    evidence = {}
    for path in paths:
        result = Results.model_validate(json.loads(path.read_text())).model_dump()
        if "MOD11C3" not in result["source"] or result["method"] != METHODS["seasonal"]:
            raise ValueError("Expected approved NASA seasonal results")
        evidence[result["region_id"]] = result
    expected = {"phoenix_study_area", *(f"phoenix_{r}" for r in (
        "northeast", "northwest", "southeast", "southwest"))}
    if set(evidence) != expected:
        raise ValueError("Incomplete Phoenix evidence")
    return evidence


def evidence_row(result):
    trend = result["trend"]
    return {"Region": result["region"],
            "Period": f"{result['period']['start']} to {result['period']['end']}",
            "Slope (°C/year)": trend["slope"] * 12, "p-value": trend["p"],
            "Direction": trend["trend"],
            "Valid months": sum(p["value"] is not None for p in result["series"]),
            "Missing months": sum(p["value"] is None for p in result["series"])}


def add_trace(figure, result, **position):
    figure.add_trace(go.Scatter(
        x=[p["time"] for p in result["series"]],
        y=[p["value"] for p in result["series"]], name=result["region"],
        mode="lines", connectgaps=False), **position)


def investigate(intent, evidence):
    main = evidence["phoenix_study_area"]
    if intent == "rank":
        selected = sorted((r for key, r in evidence.items() if key != "phoenix_study_area"),
                          key=lambda r: r["trend"]["slope"], reverse=True)
        figure = go.Figure(go.Bar(
            x=[r["region"].replace("Phoenix study area ", "").title() for r in selected],
            y=[r["trend"]["slope"] * 12 for r in selected],
            marker_color=["#f59e0b", "#38bdf8", "#38bdf8", "#38bdf8"]))
        figure.update_yaxes(title_text="Estimated warming rate (°C/year)")
        figure.update_xaxes(title_text="Phoenix subregion")
        finding = (f"{selected[0]['region']} has the highest estimated warming rate: "
                   f"{selected[0]['trend']['slope'] * 12:.3g} °C/year. "
                   "This ranking does not establish statistically significant regional differences.")
        title = "Regional warming rates · 2003–2024"
    elif intent == "compare":
        selected = [evidence[f"phoenix_{r}"] for r in ("northeast", "southwest")]
        figure = go.Figure()
        for result in selected:
            add_trace(figure, result)
        finding = (f"Northeast: {selected[0]['trend']['slope'] * 12:.3g} °C/year; "
                   f"Southwest: {selected[1]['trend']['slope'] * 12:.3g} °C/year. "
                   "The difference is descriptive; no statistical comparison of slopes was performed.")
        title = "Northeast vs. Southwest Phoenix · 2003–2024"
    elif intent == "acceleration":
        selected = []
        figure = make_subplots(rows=1, cols=2, shared_yaxes=True,
                               subplot_titles=("2003–2013", "2014–2024"))
        for column, (start, end) in enumerate((("2003-01", "2013-12"),
                                               ("2014-01", "2024-12")), 1):
            points = [p for p in main["series"] if start <= p["time"] <= end]
            # January-aligned slices preserve all calendar positions, including missing values.
            result = {**main, "series": points, "period": {"start": start, "end": end}}
            add_trace(figure, result, row=1, col=column)
            try:
                result["trend"] = run_trend([p["value"] for p in points], method="seasonal")
            except TrendInputError:
                result["trend"] = None
            selected.append(result)
        figure.update_layout(showlegend=False)
        finding = ("Verdict: Inconclusive — additional statistical testing required. "
                   "Separate seasonal trend estimates do not prove acceleration. "
                   "No slope-change test or uncertainty interval is implemented.")
        title = "Evidence Challenger · Phoenix · 2003–2024"
    elif intent == "trend":
        selected = [main]
        figure = go.Figure()
        add_trace(figure, main)
        supported = main["trend"]["p"] < 0.05 and main["trend"]["slope"] > 0
        finding = (f"Phoenix's estimated trend is {main['trend']['slope'] * 12:.3g} °C/year "
                   f"(p = {main['trend']['p']:.3g}). " +
                   ("The seasonal test supports historical warming at p < 0.05." if supported else
                    "The test does not establish significant warming; this is not proof of no change."))
        title = "Phoenix nighttime land surface temperature · 2003–2024"
    else:
        raise ValueError("Unsupported investigation")
    rows = [evidence_row(r) if r["trend"] else {
        "Region": r["region"], "Period": str(r["period"]),
        "Status": "Insufficient seasonal coverage"} for r in selected]
    if intent != "rank":
        figure.update_xaxes(title_text="Observation month")
        figure.update_yaxes(title_text="Nighttime land surface temperature (°C)")
    figure.update_layout(title=title, height=460, template="plotly_dark",
                         margin={"b": 110}, legend={"orientation": "h", "y": -0.3})
    figure.add_annotation(x=0, y=-0.22, xref="paper", yref="paper", showarrow=False,
                          text="NASA MOD11C3.061 · phoenix-qc-v1.0 · Seasonal MK / Sen's slope")
    return figure, finding, rows


def render_climate_detective():
    st.markdown("## AI Climate Detective")
    st.caption("Ask questions. Investigate climate trends. Explore the evidence.")
    st.markdown("Turn your climate questions into evidence-backed investigations.")
    st.caption("Guided Investigation Demo · Predefined workflows, local approved NASA results, "
               "and deterministic explanations. Gemini is not used.")
    for column, (label, question) in zip(st.columns(4), QUESTIONS.items(), strict=True):
        if column.button(label, key=f"detective_{label}"):
            st.session_state.detective_question = question
    question = st.text_input("Research question", key="detective_question")
    if not st.button("Investigate", type="primary", key="detective_submit"):
        return
    intent = interpret_question(question)
    if intent is None:
        st.info("This demonstration supports regional warming comparisons, historical trend "
                "analysis, and selected hypothesis investigations. Try a suggested question. "
                "Only Phoenix, 2003–2024 is supported. Hottest is different from fastest warming.")
        return
    try:
        with st.status("Following the guided investigation…", expanded=True) as status:
            st.write("✓ Selected a predefined question workflow")
            evidence = load_evidence()
            st.write("✓ Loaded contract-validated local NASA-derived observations")
            figure, finding, rows = investigate(intent, evidence)
            st.write("✓ Examined statistical evidence and generated visualization")
            status.update(label="Investigation ready", state="complete", expanded=False)
        st.markdown(f"**Research question:** {question}")
        st.plotly_chart(figure, key="detective_chart", width="stretch")
        st.markdown("**Key finding**")
        st.info(finding)
        st.markdown("**Scientific evidence**")
        st.dataframe(rows, hide_index=True, width="stretch")
        with st.expander("How was this calculated?"):
            st.write("Ranking and comparison use stored seasonal Mann–Kendall / seasonal Sen's "
                     "slope results. Monthly slopes are multiplied by 12 for °C/year. "
                     "Evidence Challenger recomputes this same validated method on two January-aligned "
                     "periods; it does not test acceleration. Missing observations remain gaps.")
            st.write(evidence["phoenix_study_area"]["source"])
            st.markdown("[NASA dataset reference](https://doi.org/10.5067/MODIS/MOD11C3.061)")
        st.caption(LIMITS)
    except (OSError, ValueError, KeyError):
        st.warning("Local investigation evidence is unavailable. Restore the committed results "
                   "and retry. The rest of the dashboard remains available.")
