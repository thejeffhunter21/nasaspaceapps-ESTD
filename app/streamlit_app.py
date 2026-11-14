"""Frontend entry point. Run with: streamlit run app/streamlit_app.py."""

import json
import os
from pathlib import Path

import streamlit as st
from api_client import DEFAULT_API_URL, ApiError, clear_results_cache, fetch_results
from charts import monthly_chart
from dotenv import load_dotenv
from view_model import build_view_model

load_dotenv(Path(__file__).resolve().parents[1] / ".env")


def show_sample(api_url):
    st.session_state.sample_fallback_url = api_url


def retry_api():
    st.session_state.sample_fallback_url = None


st.set_page_config(
    page_title="Earth System Trend Detective",
    layout="wide",
)

st.title("Earth System Trend Detective")
st.caption("Explore historical land surface temperature trends.")

api_url = os.getenv("API_URL", DEFAULT_API_URL).strip().rstrip("/")
st.session_state.setdefault("sample_fallback_url", None)
use_sample = not api_url or st.session_state.sample_fallback_url == api_url

if use_sample:
    st.caption("Local sample preview.")
    if api_url:
        st.button("Retry API", on_click=retry_api)
    sample_path = Path(__file__).resolve().parent / "fixtures/results.mock.json"
    payload = json.loads(sample_path.read_text(encoding="utf-8"))
else:
    st.button("Refresh data", on_click=clear_results_cache, args=(api_url,))
    try:
        with st.spinner("Connecting to the API. A sleeping server can take 45 seconds to respond…"):
            payload = fetch_results(api_url)
    except ApiError as exc:
        st.error(str(exc))
        st.button("Retry API", on_click=retry_api)
        st.button("Use sample data", on_click=show_sample, args=(api_url,))
        st.stop()
    st.caption("Connected to API. Successful results are cached for up to 60 seconds.")

view = build_view_model(payload)

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
st.text(view.explanation, width="stretch")
