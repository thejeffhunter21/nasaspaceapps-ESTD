"""Frontend entry point. Run with: streamlit run app/streamlit_app.py."""

import streamlit as st

st.set_page_config(
    page_title="Earth System Trend Detective",
    layout="wide",
)

st.title("Earth System Trend Detective")
st.caption("Explore historical nighttime land surface temperature in Phoenix.")
st.info("The dashboard is being prepared. Observations and trend results are not loaded yet.")
