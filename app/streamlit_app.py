"""Frontend entry point. Run with: streamlit run app/streamlit_app.py."""

import json
from pathlib import Path

import streamlit as st
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
