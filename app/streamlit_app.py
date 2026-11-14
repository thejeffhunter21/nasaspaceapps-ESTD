"""Frontend entry point. Run with: streamlit run app/streamlit_app.py."""

import json
from pathlib import Path

import streamlit as st
from charts import monthly_chart
from view_model import build_view_model

st.set_page_config(
    page_title="Earth System Trend Detective",
    layout="wide",
)

st.title("Earth System Trend Detective")
st.caption("Explore historical land surface temperature trends.")

sample_path = Path(__file__).resolve().parent / "fixtures/results.mock.json"
view = build_view_model(json.loads(sample_path.read_text(encoding="utf-8")))

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
