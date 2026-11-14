"""Frontend chart builders: draw supplied observations without fitting trends."""

from __future__ import annotations

from html import escape
from typing import TYPE_CHECKING

import plotly.graph_objects as go

if TYPE_CHECKING:
    from app.view_model import ResultsView


def monthly_chart(view: ResultsView) -> go.Figure:
    """Retain every calendar position; null values break the observed line."""
    figure = go.Figure(go.Scatter(
        x=view.times,
        y=view.values,
        mode="lines+markers",
        name="Monthly observations",
        connectgaps=False,
        hovertemplate=f"%{{x|%Y-%m}}<br>%{{y}} {escape(view.display_units)}<extra></extra>",
    ))
    figure.update_layout(
        xaxis={"title": "Month", "type": "date", "tickformat": "%Y-%m"},
        yaxis={"title": f"{view.variable} ({view.display_units})"},
        showlegend=False,
        margin={"t": 20},
    )
    return figure
