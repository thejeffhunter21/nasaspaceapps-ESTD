"""Frontend entry point. Run with: streamlit run app/streamlit_app.py."""

import json
import os
from dataclasses import replace
from pathlib import Path

import map3d
import streamlit as st
import theme
from api_client import (
    DEFAULT_API_URL,
    ApiError,
    clear_results_cache,
    fetch_region_anomaly,
    fetch_region_results,
    fetch_region_trends,
    fetch_regions,
    require_observations,
)
from charts import anomaly_chart, anomaly_heatmap, monthly_chart, region_comparison_chart
from climate_detective import render_climate_detective
from dotenv import load_dotenv
from offline_snapshot import SnapshotError, load_snapshot
from pydantic import ValidationError
from view_model import build_view_model

load_dotenv(Path(__file__).resolve().parents[1] / ".env")


def show_sample(api_url):
    st.session_state.sample_fallback_url = api_url


def retry_api():
    st.session_state.sample_fallback_url = None


def refresh_api(api_url):
    clear_results_cache(api_url, st.session_state.get("selected_region"))


def open_map_region():
    """Map click: switch the region selector to the clicked quarter before the rerun."""
    selection = st.session_state.get("phoenix_map")
    objects = (selection or {}).get("selection", {}).get("objects", {})
    for picked in objects.values():
        if picked and picked[0].get("region_id"):
            st.session_state.selected_region = picked[0]["region_id"]
            st.session_state.chart_view = "Temperature"
            return


def map_quarters(region_trends, payloads):
    """short -> plotting data for every study quarter that has complete supplied results."""
    ids = theme.quarter_ids(region_trends) if region_trends else None
    if not ids:
        return {}
    quarters = {}
    for short, rid in ids.items():
        payload = payloads.get(rid)
        if not payload:
            return {}
        try:
            view = build_view_model(payload)
        except ValidationError:
            return {}
        quarters[short] = {"region_id": rid, "label": view.region_label, "times": view.times,
                           "values": view.values, "anomaly": view.anomaly}
    return quarters


def show_failure(error, api_url, *, preview=False, snapshot=False):
    titles = {
        "empty": "No observations available",
        "empty_regions": "No regions available",
        "not_found": "No data for this region",
        "selection": "Region selection needs updating",
        "server": "The data service is unavailable",
        "timeout": "The data service is taking too long",
        "connection": "Cannot reach the data service",
        "rate_limit": "The data service is busy",
        "configuration": "The data connection needs setup",
        "sample": "The sample preview is unavailable",
        "snapshot": "The offline snapshot is unavailable",
    }
    st.error(str(error), title=titles.get(error.kind, "The data response could not be read"))
    if preview:
        st.button("Retry snapshot" if snapshot else "Retry preview")
    if api_url:
        st.button("Retry API", on_click=retry_api)
        if error.kind in ("not_found", "selection", "empty_regions"):
            st.button("Refresh regions", on_click=refresh_api, args=(api_url,))
    if not preview:
        st.button("Use sample data", on_click=show_sample, args=(api_url,))
    st.stop()


st.set_page_config(
    page_title="Earth System Trend Detective",
    page_icon="🌙",
    layout="wide",
)

st.html(theme.CSS)
st.html(theme.hero_html())

offline_root = os.getenv("OFFLINE_SNAPSHOT_DIR", "").strip()
api_url = "" if offline_root else os.getenv("API_URL", DEFAULT_API_URL).strip().rstrip("/")
region_context = f"snapshot:{Path(offline_root).resolve()}" if offline_root else api_url
st.session_state.setdefault("sample_fallback_url", None)
if st.session_state.get("region_api_url") != region_context:
    st.session_state.pop("selected_region", None)
    st.session_state.region_api_url = region_context
use_sample = not offline_root and (not api_url or st.session_state.sample_fallback_url == api_url)

render_climate_detective()
st.divider()

# Clear the previous region's evidence before any slow request starts.
evidence = st.empty()
evidence.empty()
region_trends = {}
with evidence.container():
    controls = st.container(key="controls")
    picker, status = controls.columns([3, 2], vertical_alignment="center")
    if use_sample:
        status.caption("Connection: Offline preview")
        status.caption("Local sample preview.")
        sample_path = Path(__file__).resolve().parent / "fixtures/results.mock.json"
        try:
            payload = json.loads(sample_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            show_failure(ApiError(
                "Retry the preview. If it remains unavailable, ask the demo owner to restore the sample file.",
                kind="sample",
            ), api_url, preview=True)
    else:
        if not offline_root:
            status.button("Refresh data", on_click=refresh_api, args=(api_url,))
        else:
            status.caption("Connection: Offline snapshot")
        try:
            if offline_root:
                snapshot = load_snapshot(offline_root)
                status.caption(f"Approved snapshot: {snapshot.freeze_id} | {snapshot.data_version}")
                regions = snapshot.regions
            else:
                with st.spinner("Connecting to the API. A sleeping server can take 45 seconds to respond…"):
                    regions = fetch_regions(api_url)
            labels = {region["region_id"]: region["region"] for region in regions}
            if st.session_state.get("selected_region") not in labels:
                st.session_state.selected_region = regions[0]["region_id"]
            if len(regions) > 1:
                selected_id = picker.selectbox(
                    "Region", options=list(labels), format_func=labels.get, key="selected_region",
                )
            else:
                selected_id = regions[0]["region_id"]
                picker.caption(f"Region: {labels[selected_id]}")
            if selected_id not in labels:
                raise ApiError("Choose a region from the refreshed list.", kind="selection")
            if offline_root:
                payload = snapshot.results[selected_id]
                region_trends = {rid: {"region": result["region"], **result["trend"]}
                                 for rid, result in snapshot.results.items()}
            else:
                with st.spinner("Loading the selected region…"):
                    payload = fetch_region_results(api_url, selected_id)
                region_trends = fetch_region_trends(api_url)
        except SnapshotError as exc:
            show_failure(ApiError(str(exc), kind="snapshot"), "", preview=True, snapshot=True)
        except ApiError as exc:
            show_failure(exc, api_url)

    try:
        require_observations(payload)
        view = build_view_model(payload)
    except ApiError as exc:
        show_failure(exc, api_url, preview=use_sample)
    except ValidationError:
        show_failure(ApiError(
            "Required result fields are missing or invalid. Retry; do not treat missing statistics as zero.",
            kind="sample" if use_sample else "invalid_response",
        ), api_url, preview=use_sample)

    if use_sample and api_url:
        status.button("Retry API", on_click=retry_api)
    if not use_sample and not offline_root:
        status.caption("Connection: Live API")
        status.caption("Connected to API. Successful results are cached for up to 60 seconds.")
        if view.anomaly is None:
            with st.spinner("Loading the month-by-month comparison…"):
                anomaly = fetch_region_anomaly(api_url, view.region_id, view.times)
            if anomaly is not None and all(
                (a is None) == (v is None) for a, v in zip(anomaly, view.values)
            ):
                view = replace(view, anomaly=anomaly)

    quarter_payloads = {}
    if offline_root and not use_sample:
        quarter_payloads = snapshot.results
    elif not use_sample and api_url and theme.quarter_ids(region_trends):
        try:
            with st.spinner("Loading the Phoenix map…"):
                for rid in theme.quarter_ids(region_trends).values():
                    quarter = fetch_region_results(api_url, rid)
                    anomaly_values = fetch_region_anomaly(api_url, rid, tuple(
                        point["time"] for point in quarter["series"]))
                    if anomaly_values is not None:
                        quarter = {**quarter, "anomaly": [
                            {"time": point["time"], "value": a}
                            for point, a in zip(quarter["series"], anomaly_values)]}
                    quarter_payloads[rid] = quarter
        except ApiError:
            quarter_payloads = {}  # the map is optional; the evidence below still loads
    quarters = map_quarters(region_trends, quarter_payloads)
    if quarters:
        selected_quarter = next((q for q, data in quarters.items()
                                 if data["region_id"] == view.region_id), None)
        st.html(theme.section_html(
            "Explore the city", "Phoenix from above",
            "Every bar is one real month of NASA satellite data: taller is hotter, orange is warmer "
            "than usual for that month, blue is cooler. In each quarter, years run west to east "
            "and months north to south, so a bar's spot inside its quarter is a calendar position, "
            "not a street location. Missing months have no bar. Click a quarter to open its charts.",
        ))
        map_mode = st.radio(
            "Bars", ("Every month, 2003–2024", "Latest month"), horizontal=True, key="map_mode",
            help="Latest month is the newest observation in the approved data (not live weather).",
        )
        with st.container(key="mapwrap"):
            st.pydeck_chart(
                map3d.build_deck(quarters, selected_quarter,
                                 "latest" if map_mode == "Latest month" else "months"),
                height=560, key="phoenix_map", on_select=open_map_region,
                selection_mode="single-object",
            )
        st.caption("Map: freeways from Natural Earth (public domain); street basemap © CARTO, "
                   "© OpenStreetMap contributors, shown when online. Data: NASA MOD11C3 v061.")

    if view.is_sample:
        st.warning("Sample data — synthetic observations for previewing the dashboard.")

    st.html(theme.section_html("The verdict", ""))
    st.subheader(view.region_label)
    st.caption(f"{view.variable} ({view.display_units}) | {view.period_label}")
    st.html(theme.verdict_html(view))

    slope_card, p_card, direction_card = st.columns(3)
    slope_card.metric(f"Slope ({view.display_slope_unit})", view.display_slope, border=True)
    p_card.metric("p-value", view.display_p, border=True)
    direction_card.metric("Direction", view.direction, border=True)
    st.caption(
        "Statistically significant (p < 0.05)."
        if view.significant
        else "Not statistically significant (p >= 0.05)."
    )
    st.html(theme.facts_html(view))

    anomaly_figure = anomaly_chart(view)
    chart_view = "Temperature"
    st.html(theme.section_html("The evidence", "Month by month"))
    if anomaly_figure is not None:
        chart_view = st.radio(
            "Show", ("Temperature", "Anomaly"), horizontal=True, key="chart_view",
            help="Anomaly = each month minus the average for that calendar month over the period.",
        )
    if chart_view == "Anomaly":
        st.html(theme.note_html(
            f"Each dot is one month minus the {view.baseline_label} average for that same calendar "
            f"month, in {view.display_units}. Zero (dashed line) means a normal month for its "
            "season; above zero is warmer than usual.",
        ))
        st.plotly_chart(
            anomaly_figure, width="stretch", theme=None, config={"displaylogo": False},
            alt=(f"Monthly anomaly in {view.region_label}, {view.period_label}, in "
                 f"{view.display_units} relative to the {view.baseline_label} calendar-month "
                 f"mean, with a zero line. Missing months: "
                 f"{sum(value is None for value in view.anomaly)}; gaps indicate missing "
                 "observations."),
        )
    else:
        st.html(theme.note_html(
            "Every dot is one month of satellite measurements. The big up-and-down wave is "
            "summer and winter; the trend is the slow drift underneath it.",
        ))
        st.plotly_chart(
            monthly_chart(view),
            width="stretch",
            theme=None,
            config={"displaylogo": False},
            alt=(
                f"Monthly {view.variable.lower()} in {view.region_label}, {view.period_label}, "
                f"in {view.display_units}. Direction: {view.direction}; "
                f"slope {view.display_slope} {view.display_slope_unit}; "
                f"{'statistically significant' if view.significant else 'not statistically significant'} "
                f"at p < 0.05. Missing months: {sum(value is None for value in view.values)}; "
                "gaps indicate missing observations."
            ),
        )
    st.caption("Gaps indicate missing observations.")

    heatmap = anomaly_heatmap(view)
    if heatmap is not None:
        swing = view.seasonal_swing
        swing_text = (f" Here the warmest and coolest months differ by about {swing:.0f} "
                      f"{view.display_units} on average." if swing is not None else "")
        st.html(theme.section_html(
            "How the detective sees it", "Same month, every year",
            f"Each square compares one month with the {view.baseline_label} average for that same "
            "calendar month, so a July is only compared with other Julys. The seasonal test works the same "
            "way, which lets it find a slow trend hidden under the summer–winter swing."
            + swing_text + " Blank squares are missing months.",
        ))
        st.plotly_chart(
            heatmap, width="stretch", theme=None, config={"displaylogo": False},
            alt=(f"Grid of monthly differences from each calendar month's average in "
                 f"{view.region_label}, rows by year and columns by month, in "
                 f"{view.display_units}; blue is cooler than usual, orange warmer."),
        )

    if not view.is_sample and len(region_trends) > 1 and view.region_id in region_trends:
        st.html(theme.section_html(
            "Across the city", "Which part of Phoenix is warming fastest?",
            "The same test run on each quarter of the study area. The highlighted region is "
            "the one selected above.",
        ))
        quarter_map = theme.quarter_map_html(region_trends, view.region_id)
        comparison = region_comparison_chart(region_trends, view.region_id)
        if quarter_map and comparison is not None:
            map_col, chart_col = st.columns([2, 3], vertical_alignment="center")
            map_col.html(quarter_map)
            chart_col.plotly_chart(comparison, width="stretch", theme=None,
                                   config={"displaylogo": False},
                                   alt="Bar chart of supplied trend slopes for every region.")
        elif comparison is not None:
            st.plotly_chart(comparison, width="stretch", theme=None,
                            config={"displaylogo": False},
                            alt="Bar chart of supplied trend slopes for every region.")

    st.html(theme.section_html("In plain words", "Explanation"))
    with st.container(key="explanation"):
        st.caption(
            f'{"Automatic summary"} (AI unavailable)'
            if view.explanation_source == "fallback"
            else "AI-assisted explanation"
        )
        st.text(view.explanation, width="stretch")

    st.html(theme.section_html("Read this before quoting us", "What this can and can’t tell you"))
    st.html(theme.limits_html(view))
    st.write("")

    with st.expander("Source, method and definitions"):
        st.caption(f"Source: {view.source}")
        st.caption(f"Method: {view.method}")
        st.caption(f"Period: {view.period_label}")
        st.markdown(
            "**Slope:** the estimated rate of change over the full stated period, "
            f"in {view.display_slope_unit}. Positive values indicate an increase; negative "
            "values indicate a decrease. The slope is not a forecast."
        )
        st.markdown(
            "**p-value:** how unusual a result at least this extreme would be if "
            "there were no underlying trend, under the test's assumptions. Below "
            "0.05 is statistically significant here. At or above 0.05 means "
            "insufficient evidence of a trend, not proof of no change."
        )
        st.markdown(
            "**Data labels:** Live API describes the connection, not live measurements. "
            "Offline snapshot reads approved real files without an API. "
            "Offline preview uses a local sample file. Sample data identifies synthetic "
            "observations, whether received from the API or read locally."
        )
    st.html(theme.footer_html())
