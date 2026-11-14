"""Frontend entry point. Run with: streamlit run app/streamlit_app.py."""

import json
import os
from pathlib import Path

import streamlit as st
from api_client import (
    DEFAULT_API_URL,
    ApiError,
    clear_results_cache,
    fetch_region_results,
    fetch_regions,
    require_observations,
)
from charts import monthly_chart
from dotenv import load_dotenv
from pydantic import ValidationError
from view_model import build_view_model

load_dotenv(Path(__file__).resolve().parents[1] / ".env")


def show_sample(api_url):
    st.session_state.sample_fallback_url = api_url


def retry_api():
    st.session_state.sample_fallback_url = None


def refresh_api(api_url):
    clear_results_cache(api_url, st.session_state.get("selected_region"))


def show_failure(error, api_url, *, preview=False):
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
    }
    st.error(str(error), title=titles.get(error.kind, "The data response could not be read"))
    if preview:
        st.button("Retry preview")
    if api_url:
        st.button("Retry API", on_click=retry_api)
        if error.kind in ("not_found", "selection", "empty_regions"):
            st.button("Refresh regions", on_click=refresh_api, args=(api_url,))
    if not preview:
        st.button("Use sample data", on_click=show_sample, args=(api_url,))
    st.stop()


st.set_page_config(
    page_title="Earth System Trend Detective",
    layout="wide",
)

st.title("Earth System Trend Detective")
st.caption("Explore historical land surface temperature trends.")

api_url = os.getenv("API_URL", DEFAULT_API_URL).strip().rstrip("/")
st.session_state.setdefault("sample_fallback_url", None)
if st.session_state.get("region_api_url") != api_url:
    st.session_state.pop("selected_region", None)
    st.session_state.region_api_url = api_url
use_sample = not api_url or st.session_state.sample_fallback_url == api_url

# Clear the previous region's evidence before any slow request starts.
evidence = st.empty()
evidence.empty()
with evidence.container():
    if use_sample:
        st.caption("Connection: Offline preview")
        st.caption("Local sample preview.")
        sample_path = Path(__file__).resolve().parent / "fixtures/results.mock.json"
        try:
            payload = json.loads(sample_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            show_failure(ApiError(
                "Retry the preview. If it remains unavailable, ask the demo owner to restore the sample file.",
                kind="sample",
            ), api_url, preview=True)
    else:
        st.button("Refresh data", on_click=refresh_api, args=(api_url,))
        try:
            with st.spinner("Connecting to the API. A sleeping server can take 45 seconds to respond…"):
                regions = fetch_regions(api_url)
            labels = {region["region_id"]: region["region"] for region in regions}
            if st.session_state.get("selected_region") not in labels:
                st.session_state.selected_region = regions[0]["region_id"]
            if len(regions) > 1:
                selected_id = st.selectbox(
                    "Region", options=list(labels), format_func=labels.get, key="selected_region",
                )
            else:
                selected_id = regions[0]["region_id"]
            if selected_id not in labels:
                raise ApiError("Choose a region from the refreshed list.", kind="selection")
            with st.spinner("Loading the selected region…"):
                payload = fetch_region_results(api_url, selected_id)
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
        st.button("Retry API", on_click=retry_api)
    if not use_sample:
        st.caption("Connection: Live API")
        st.caption("Connected to API. Successful results are cached for up to 60 seconds.")

    if view.is_sample:
        st.warning("Sample data — synthetic observations for previewing the dashboard.")

    st.subheader(view.region_label)
    st.caption(f"{view.variable} ({view.units}) | {view.period_label}")

    st.subheader("Trend summary")
    with st.container(horizontal=True):
        st.metric(f"Slope ({view.slope_unit})", str(view.slope), border=True)
        st.metric("p-value", str(view.p), border=True)
        st.metric("Direction", view.direction, border=True)
    st.caption(
        "Statistically significant (p < 0.05)."
        if view.significant
        else "Not statistically significant (p >= 0.05)."
    )

    st.subheader("Monthly observations")
    st.plotly_chart(
        monthly_chart(view),
        width="stretch",
        alt=(
            f"Monthly {view.variable.lower()} in {view.region_label}, {view.period_label}, "
            f"in {view.units}. Gaps indicate missing observations."
        ),
    )
    st.caption("Gaps indicate missing observations.")

    st.subheader("Explanation")
    st.caption(
        "Automatic summary (AI unavailable)"
        if view.explanation_source == "fallback"
        else "AI-assisted explanation"
    )
    st.text(view.explanation, width="stretch")

    with st.expander("Source, method and definitions"):
        st.caption(f"Source: {view.source}")
        st.caption(f"Method: {view.method}")
        st.caption(f"Period: {view.period_label}")
        st.markdown(
            "**Slope:** the estimated rate of change over the full stated period, "
            f"in {view.slope_unit}. Positive values indicate an increase; negative "
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
            "Offline preview uses a local file. Sample data identifies synthetic "
            "observations, whether received from the API or read locally."
        )
