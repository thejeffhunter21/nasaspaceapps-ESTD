"""Keep frontend checks independent of deployment settings and real services."""

import pytest
import requests
import streamlit as st


@pytest.fixture(autouse=True)
def isolated_frontend(monkeypatch):
    monkeypatch.setenv("API_URL", "")
    monkeypatch.setattr("dotenv.load_dotenv", lambda *args, **kwargs: None)
    st.cache_data.clear()

    def block_network(*args, **kwargs):
        raise AssertionError("Frontend unit tests must mock HTTP requests")

    monkeypatch.setattr(requests.Session, "request", block_network)
    yield
    st.cache_data.clear()
