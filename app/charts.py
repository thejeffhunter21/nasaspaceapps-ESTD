"""Frontend chart builders: draw supplied observations without fitting trends."""

from __future__ import annotations

from html import escape
from typing import TYPE_CHECKING

import numpy as np
import plotly.graph_objects as go

if TYPE_CHECKING:
    from app.view_model import ResultsView

TEXT = "#EAEEF9"
MUTED = "#A3ADCB"
GRID = "rgba(150, 168, 220, 0.12)"
FONT = 'ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, Arial, sans-serif'
# Night-to-heat scale for observed temperatures.
HEAT_SCALE = [[0.0, "#3B6FD8"], [0.3, "#62B4FF"], [0.55, "#FFC857"], [0.8, "#FF8A3D"],
              [1.0, "#E8453C"]]
# Blue/orange diverging scale for differences from the monthly average (colour-blind safe).
DIVERGING = [[0.0, "#2B6CB0"], [0.25, "#62B4FF"], [0.5, "#1B2440"], [0.75, "#FF9A4D"],
             [1.0, "#E8453C"]]
MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


def _base_layout(**extra) -> dict:
    layout = {
        "paper_bgcolor": "rgba(0,0,0,0)",
        "plot_bgcolor": "rgba(0,0,0,0)",
        "font": {"size": 14, "color": TEXT, "family": FONT},
        "hoverlabel": {"bgcolor": "#121A30", "bordercolor": "#FFC857",
                       "font": {"color": TEXT, "family": FONT}},
        "showlegend": False,
    }
    layout.update(extra)
    return layout


def _axis(title: str, **extra) -> dict:
    axis = {"title": {"text": title, "font": {"color": MUTED, "size": 13}},
            "gridcolor": GRID, "zeroline": False, "linecolor": GRID,
            "tickfont": {"color": MUTED}, "automargin": True}
    axis.update(extra)
    return axis


def monthly_chart(view: ResultsView) -> go.Figure:
    """Retain every calendar position; null values break the observed line."""
    figure = go.Figure(go.Scatter(
        x=view.times,
        y=view.values,
        mode="lines+markers",
        name="Monthly observations",
        connectgaps=False,
        line={"color": "rgba(234, 238, 249, 0.38)", "width": 1.6},
        # Colour only: a numeric copy (NaN for gaps); y keeps the supplied nulls.
        marker={"size": 6, "color": np.array([np.nan if v is None else v for v in view.values],
                                             dtype=float), "colorscale": HEAT_SCALE,
                "line": {"width": 0}, "showscale": False},
        hovertemplate=f"%{{x|%Y-%m}}<br>%{{y}} {escape(view.display_units)}<extra></extra>",
    ))
    # Faint bands mark missing months so a gap reads as "no observation", not a glitch.
    for time, value in zip(view.times, view.values):
        if value is None:
            figure.add_vrect(x0=f"{time}-01", x1=f"{time}-28", line_width=0,
                             fillcolor="rgba(255, 200, 87, 0.22)", layer="below")
    figure.update_layout(**_base_layout(
        title={"text": f"{escape(view.region_label)}: monthly temperature ({escape(view.display_units)})",
               "font": {"size": 15, "color": TEXT}, "x": 0.01},
        xaxis=_axis("Month", type="date", tickformat="%Y", nticks=12, showspikes=True,
                    spikecolor="#FFC857", spikethickness=1, spikedash="dot"),
        yaxis=_axis(f"{view.variable} ({view.display_units})"),
        margin={"t": 50, "b": 60, "l": 10, "r": 10},
        height=430,
        hovermode="x",
    ))
    return figure


def anomaly_chart(view: ResultsView) -> go.Figure | None:
    """Supplied anomalies (value minus the calendar-month mean); gaps stay gaps."""
    if not view.anomaly or len(view.anomaly) != len(view.times):
        return None
    unit = escape(view.display_units)
    colors = np.array([np.nan if v is None else v for v in view.anomaly], dtype=float)
    present = [abs(v) for v in view.anomaly if v is not None]
    limit = max(present) if present else 1.0
    figure = go.Figure(go.Scatter(
        x=view.times,
        y=view.anomaly,
        mode="lines+markers",
        name="Monthly anomaly",
        connectgaps=False,
        line={"color": "rgba(234, 238, 249, 0.30)", "width": 1.4},
        marker={"size": 6, "color": colors, "colorscale": DIVERGING, "cmid": 0,
                "cmin": -limit, "cmax": limit, "line": {"width": 0}},
        hovertemplate=(f"%{{x|%Y-%m}}<br>%{{y:+.4f}} {unit} vs the {view.baseline_label} "
                       "mean for that calendar month<extra></extra>"),
    ))
    for time, value in zip(view.times, view.anomaly):
        if value is None:
            figure.add_vrect(x0=f"{time}-01", x1=f"{time}-28", line_width=0,
                             fillcolor="rgba(255, 200, 87, 0.22)", layer="below")
    figure.add_hline(y=0, line={"color": "#FFC857", "width": 1.5, "dash": "dash"},
                     annotation_text=f"0 = {view.baseline_label} calendar-month mean",
                     annotation_position="top left",
                     annotation_font={"color": "#FFC857", "size": 12})
    figure.update_layout(**_base_layout(
        title={"text": (f"{escape(view.region_label)}: monthly anomaly ({unit}) "
                        f"vs {view.baseline_label} calendar-month mean"),
               "font": {"size": 15, "color": TEXT}, "x": 0.01},
        xaxis=_axis("Month", type="date", tickformat="%Y", nticks=12),
        yaxis=_axis(f"Anomaly ({unit})"),
        margin={"t": 50, "b": 60, "l": 10, "r": 10},
        height=430,
        hovermode="x",
    ))
    return figure


def anomaly_heatmap(view: ResultsView) -> go.Figure | None:
    """Year x calendar-month grid of supplied anomalies; missing months stay blank."""
    if not view.anomaly or len(view.anomaly) != len(view.times):
        return None
    years = sorted({time[:4] for time in view.times})
    grid = {year: [None] * 12 for year in years}
    for time, value in zip(view.times, view.anomaly):
        grid[time[:4]][int(time[5:7]) - 1] = value
    present = [abs(v) for v in view.anomaly if v is not None]
    if not present:
        return None
    limit = max(present)
    unit = escape(view.display_units)
    figure = go.Figure(go.Heatmap(
        z=[grid[year] for year in years],
        x=list(MONTHS),
        y=years,
        zmid=0, zmin=-limit, zmax=limit,
        colorscale=DIVERGING,
        xgap=3, ygap=3,
        hoverongaps=False,
        colorbar={"title": {"text": f"{unit} vs<br>monthly<br>average", "font": {"color": MUTED}},
                  "tickfont": {"color": MUTED}, "outlinewidth": 0, "thickness": 12},
        hovertemplate=f"%{{x}} %{{y}}<br>%{{z:+.2f}} {unit} vs that month's average<extra></extra>",
    ))
    figure.update_layout(**_base_layout(
        xaxis=_axis("", side="top", showgrid=False, fixedrange=True),
        yaxis=_axis("Year", autorange="reversed", showgrid=False, fixedrange=True, dtick=2,
                    type="category"),
        margin={"t": 40, "b": 20, "l": 10, "r": 10},
        height=max(360, 22 * len(years) + 80),
    ))
    return figure


def region_comparison_chart(trends: dict, selected_id: str) -> go.Figure | None:
    """Supplied per-month slopes for every region; words carry significance, not colour."""
    if len(trends) < 2:
        return None
    ordered = sorted(trends.items(), key=lambda item: item[1]["slope"])
    labels = [t["region"] for _, t in ordered]
    slopes = [t["slope"] for _, t in ordered]
    units = {t["slope_unit"] for _, t in ordered}
    unit = next(iter(units)).replace("degC", "°C") if len(units) == 1 else "supplied units"
    colors = ["#FFC857" if rid == selected_id else ("#FF8A3D" if t["slope"] > 0 else "#62B4FF")
              for rid, t in ordered]
    text = [f"{t['slope']:.4g} · {'significant' if t['p'] < 0.05 else 'not significant'}"
            for _, t in ordered]
    figure = go.Figure(go.Bar(
        x=slopes, y=labels, orientation="h", marker={"color": colors, "line": {"width": 0}},
        text=text, textposition="auto", insidetextanchor="end",
        insidetextfont={"color": "#0A0F1E", "family": FONT},
        outsidetextfont={"color": TEXT, "family": FONT},
        hovertemplate=f"%{{y}}<br>%{{x:.5g}} {escape(unit)}<extra></extra>",
    ))
    figure.update_layout(**_base_layout(
        xaxis=_axis(f"Trend slope ({unit})", rangemode="tozero"),
        yaxis=_axis("", showgrid=False),
        margin={"t": 10, "b": 70, "l": 10, "r": 10},
        height=100 + 52 * len(labels),
        bargap=0.35,
    ))
    return figure
