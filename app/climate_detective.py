"""Guided scientific investigations using approved, local Phoenix observations."""

import json
import re
from pathlib import Path

import plotly.graph_objects as go
import streamlit as st
from discovery_evidence import calculate_cell_trends, retrieve_cells, select_cell
from plotly.subplots import make_subplots

from earth_system_trend.ai.trend import METHODS, TrendInputError, run_trend
from earth_system_trend.contract import Results

ROOT = Path(__file__).resolve().parents[1]
QUESTIONS = {
    "Find a hidden warming pattern": "Find a warming pattern that regional averages might hide.",
    "Which region is warming fastest?": "Which Phoenix region is warming fastest?",
    "Compare a local observation with its regional average":
        "Compare a local observation with its regional average.",
    "Has Phoenix warming accelerated?": "Has Phoenix warming accelerated since 2014?",
}
DISCLOSURE = (
    "Prototype Discovery Engine — this demonstration uses deterministic investigation workflows "
    "to represent the planned retrieval-augmented scientific analysis architecture. Scientific "
    "results shown are derived from verified project data where available."
)

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
        "accelerated acceleration trend trends show me please evidence for "
        "find hidden pattern patterns that regional averages might hide discover localized local "
        "observation observations with its average can warming most"
    )
    if not set(re.findall(r"[a-z]+", q)) <= set(vocabulary.split()):
        return None
    years = re.findall(r"\b\d+\b", q)
    compass = [r for r in ("northeast", "southwest", "northwest", "southeast") if r in q]
    if "accelerat" in q:
        return "acceleration" if not compass and years in ([], ["2014"]) else None
    if years not in ([], ["2003"], ["2003", "2024"]):
        return None
    if re.search(r"\bregional average\b", q) or "compare local" in q:
        return "local_vs_region" if not compass else None
    if any(word in q for word in ("hidden", "hide", "discover", "pattern", "localized", "local warming")):
        return "hidden_pattern" if not compass else None
    if "compare" in q or " vs " in q or "versus" in q:
        return "compare" if set(compass) == {"northeast", "southwest"} else None
    if compass:
        return None
    if any(word in q for word in ("fastest", "warmed most", "warming most", "most nighttime warming")):
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
            "Direction": trend["trend"], "Kendall tau": trend["tau"],
            "Significant (p < 0.05)": trend["p"] < 0.05,
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


def run_discovery(intent, evidence):
    """Return computed evidence and an honest account of the operations executed."""
    metadata = {
        "Source": "NASA Terra/MODIS MOD11C3 Collection 6.1",
        "Variable": "Nighttime land surface temperature (°C)",
        "Study area": "Phoenix fixed study window; not city boundaries",
        "Analysis period": "2003-01 to 2024-12",
        "Provenance": "Existing processed ESTD dataset, phoenix-qc-v1.0",
        "Method": METHODS["seasonal"],
    }
    tools = ["load_evidence(): validated committed regional results"]
    challenge = "Descriptive slope differences do not establish statistically different warming rates."
    conclusion = "Descriptive evidence; significant differences between slopes are not established."
    matters = "Regional summaries can conceal spatial variation worth investigating."
    if intent in ("hidden_pattern", "local_vs_region"):
        try:
            processed = ROOT / "data/processed"
            cells, manifest = retrieve_cells(
                (processed / "grid_cells.csv").read_bytes(),
                (processed / "grid_cells_manifest.json").read_bytes())
            trends = calculate_cell_trends(cells)
            cell, trend, region, difference = select_cell(cells, trends, evidence)
            local = {"region": f"MODIS cell {cell['cell_id']}", "series": cell["series"],
                     "period": region["period"], "trend": trend}
            figure = go.Figure()
            add_trace(figure, local)
            add_trace(figure, region)
            rows = [evidence_row(local), evidence_row(region)]
            rows[0].update({"Cell ID": cell["cell_id"], "Latitude": cell["lat"],
                            "Longitude": cell["lon"], "Containing region": region["region"],
                            "Slope difference (°C/year)": difference})
            figure.update_layout(title=f"Cell {cell['cell_id']} vs. {region['region']} · 2003–2024",
                                 template="plotly_dark", height=460,
                                 legend={"orientation": "h", "y": -0.25})
            figure.update_xaxes(title_text="Observation month")
            figure.update_yaxes(title_text="Nighttime land surface temperature (°C)")
            finding = (f"Cell {cell['cell_id']} ({cell['lat']:.3f}°, {cell['lon']:.3f}°) has an "
                       f"estimated trend of {trend['slope'] * 12:.3g} °C/year, versus "
                       f"{region['trend']['slope'] * 12:.3g} °C/year for {region['region']}. "
                       f"The estimated difference is {difference:+.3g} °C/year.")
            metadata.update({"Granularity": "Individual quality-controlled MODIS grid cells",
                             "Cells examined": len(cells), "Eligible seasonal trends": len(trends),
                             "Cell-month positions retrieved": sum(len(c["series"]) for c in cells.values()),
                             "Missing cell-month values": sum(p["value"] is None
                                 for c in cells.values() for p in c["series"]),
                             "Snapshot SHA-256": manifest["sha256"],
                             "Selected cell": cell["cell_id"]})
            tools += ["retrieve_cells(): verified manifest hash, cell metadata and full calendars",
                      "calculate_cell_trends(): seasonal Mann–Kendall / Sen's slope for eligible cells",
                      "select_cell(): largest estimated cell-minus-containing-region slope difference"]
            challenge = ("This cell was selected after scanning eligible cells for the largest slope "
                         "difference. Selection and multiple comparisons make this exploratory. "
                         "Cell and regional series overlap. Individual trend p-values do not test "
                         "their difference; no spatial-dependence or multiple-testing correction is applied.")
            conclusion = "Exploratory candidate for deeper investigation; a significant slope difference is not established."
        except (OSError, ValueError, KeyError, TypeError):
            # Invalid granular evidence must degrade visibly, never become invented cells.
            metadata["Granularity"] = "Regional observations only; grid retrieval unavailable or invalid"
            metadata["Grid status"] = (
                "Granular cell-level investigation unavailable in this build; demonstrating "
                "the discovery workflow using verified regional observations.")
            selected = max((r for key, r in evidence.items() if key != "phoenix_study_area"),
                           key=lambda r: r["trend"]["slope"])
            main = evidence["phoenix_study_area"]
            figure = go.Figure()
            add_trace(figure, selected)
            add_trace(figure, main)
            figure.update_layout(title="Regional discovery fallback · Phoenix · 2003–2024", height=460)
            figure.update_xaxes(title_text="Observation month")
            figure.update_yaxes(title_text="Nighttime land surface temperature (°C)")
            rows = [evidence_row(selected), evidence_row(main)]
            finding = (f"{selected['region']} has the highest estimated regional warming rate "
                       f"({selected['trend']['slope'] * 12:.3g} °C/year), versus "
                       f"{main['trend']['slope'] * 12:.3g} °C/year for the whole study area.")
            tools += ["Selected the largest stored regional slope; compared with the study-area average"]
    else:
        figure, finding, rows = investigate(intent, evidence)
        metadata["Granularity"] = "Regional temperature observations"
        if intent == "acceleration":
            tools += ["Split observations into January-aligned 2003–2013 and 2014–2024 periods",
                      "run_trend(): recomputed seasonal trends without dropping missing positions"]
            challenge = "Two different estimated slopes do not, by themselves, prove that the warming rate changed."
            conclusion = "INCONCLUSIVE — an appropriate slope-change test is required before claiming acceleration."
            matters = "Challenging an attractive interpretation helps prevent unsupported conclusions."
        else:
            tools += ["investigate(): selected stored seasonal statistics and generated the chart"]
    if intent in ("hidden_pattern", "local_vs_region"):
        figure.update_layout(margin={"b": 110})
        figure.add_annotation(x=0, y=-0.2, xref="paper", yref="paper", showarrow=False,
                              text="NASA MOD11C3.061 · 2003–2024 · Seasonal MK / Sen's slope")
    tools += ["Evidence checks: units, coverage, and comparison-test availability",
              "Plotly: generated chart from retrieved data; missing observations remain gaps"]
    return {"figure": figure, "finding": finding, "rows": rows, "metadata": metadata,
            "tools": tools, "challenge": challenge, "conclusion": conclusion, "matters": matters}


def render_climate_detective():
    st.markdown("## AI Scientific Discovery Engine")
    st.caption("Explore patterns hidden beneath regional climate averages.")
    st.markdown("The dashboard shows what is happening. The AI layer is designed to investigate "
                "what is hidden beneath it.")
    st.caption("Prototype workflow — deterministic routing demonstrates the planned "
               "retrieval-augmented scientific analysis architecture. No Gemini or vector database is used.")
    st.markdown("**Question → Retrieval → Investigation → Statistical validation → Discovery → Visualization**")
    for column, (label, question) in zip(st.columns(4), QUESTIONS.items(), strict=True):
        if column.button(label, key=f"detective_{label}"):
            st.session_state.detective_question = question
    question = st.text_input("Research question", key="detective_question",
                             placeholder="Ask the AI to investigate the Phoenix climate data...")
    submitted = st.button("Investigate", type="primary", key="detective_submit")
    if not submitted:
        st.caption(DISCLOSURE)
        return
    intent = interpret_question(question)
    if intent is None:
        st.info("This prototype supports hidden-pattern discovery, regional ranking, local vs. "
                "regional comparison, and acceleration since 2014. Try a suggested question. "
                "Only Phoenix, 2003–2024 is supported. Hottest is different from fastest warming.")
        st.caption(DISCLOSURE)
        return
    try:
        st.markdown("**Research question**")
        st.write(question)
        with st.status("RETRIEVE → INVESTIGATE → VALIDATE → DISCOVER", expanded=True) as status:
            st.write(f"1. Understanding research question · deterministic intent: {intent}")
            evidence = load_evidence()
            st.write("2. Retrieved local NASA MOD11C3 nighttime surface-temperature evidence · Phoenix · 2003–2024")
            result = run_discovery(intent, evidence)
            if "Cells examined" in result["metadata"]:
                st.write(f"Retrieved {result['metadata']['Cells examined']} real cells · "
                         f"{result['metadata']['Cell-month positions retrieved']} cell-month positions · "
                         f"{result['metadata']['Missing cell-month values']} missing values retained")
            st.write("3. Scientific analysis · " + result["tools"][1])
            st.write("4. Challenging the finding · descriptive differences require a comparison test")
            st.write("5. Verified evidence prepared for visualization")
            status.update(label="Investigation complete · inspect the evidence below", state="complete")
        if "Grid status" in result["metadata"]:
            st.warning(result["metadata"]["Grid status"])
        if intent == "acceleration":
            st.markdown("**Hypothesis:** Recent nighttime warming is faster than earlier warming.")
        st.plotly_chart(result["figure"], key="detective_chart", width="stretch")
        st.markdown("**Discovery · Key finding**")
        st.info(result["finding"])
        if "Selected cell" in result["metadata"]:
            cell_metric, region_metric, delta_metric = st.columns(3)
            cell_metric.metric("Cell trend (°C/year)", f"{result['rows'][0]['Slope (°C/year)']:.3g}")
            region_metric.metric("Regional trend (°C/year)", f"{result['rows'][1]['Slope (°C/year)']:.3g}")
            delta_metric.metric("Descriptive difference (°C/year)",
                                f"{result['rows'][0]['Slope difference (°C/year)']:+.3g}")
        st.markdown("**Evidence**")
        st.dataframe(result["rows"], hide_index=True, width="stretch")
        st.markdown("**Challenge**")
        st.write(result["challenge"])
        st.markdown("**Conclusion**")
        st.write(result["conclusion"])
        st.markdown("**Why it matters**")
        st.write(result["matters"])
        with st.expander("Retrieved Evidence"):
            for label, value in result["metadata"].items():
                st.write(f"**{label}:** {value}")
            st.write(evidence["phoenix_study_area"]["source"])
            st.markdown("[NASA dataset reference](https://doi.org/10.5067/MODIS/MOD11C3.061)")
        with st.expander("Investigation Tools"):
            st.caption("Actual Python operations; deterministic workflow selection, not LLM tool calling.")
            for tool in result["tools"]:
                st.write(f"✓ {tool}")
        with st.expander("How was this calculated?"):
            st.write("Existing seasonal Mann–Kendall and seasonal Sen's slope; monthly slopes × 12 "
                     "give °C/year. Cell series retain every calendar position. The local example "
                     "is selected by the largest cell-minus-containing-region slope. No slope-difference "
                     "test, causal analysis, forecast, or autonomous hypothesis generation is implemented.")
        st.caption(LIMITS)
    except (OSError, ValueError, KeyError):
        st.warning("Local investigation evidence is unavailable. Restore the committed results "
                   "and retry. The rest of the dashboard remains available.")
    st.caption(DISCLOSURE)
