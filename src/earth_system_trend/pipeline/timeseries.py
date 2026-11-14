"""Read the Data layer's monthly CSV (columns: time as YYYY-MM, value)."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

MIN_VALID_MONTHS = 24


class SeriesError(ValueError):
    """The CSV is missing, malformed, or too short to test."""


def load_series(path: str | Path) -> tuple[list[str], list[float | None]]:
    """Return (months, values) in order, with None for every missing month."""
    path = Path(path)
    if not path.exists():
        raise SeriesError(f"{path}: file not found")
    df = pd.read_csv(path)
    if "time" not in df.columns and "date" in df.columns:
        df = df.rename(columns={"date": "time"})  # older Data layer files call it "date"
    for column in ("time", "value"):
        if column not in df.columns:
            raise SeriesError(f"{path}: missing column '{column}' (need time, value)")
    try:
        months = pd.PeriodIndex(pd.to_datetime(df["time"].astype(str), format="mixed"), freq="M")
    except (ValueError, TypeError) as exc:
        raise SeriesError(f"{path}: unreadable date in 'time' ({exc})") from exc
    if months.duplicated().any():
        raise SeriesError(f"{path}: duplicate month {months[months.duplicated()][0]}")
    values = pd.to_numeric(df["value"], errors="coerce")
    series = pd.Series(values.to_numpy(), index=months).sort_index()
    full = pd.period_range(series.index.min(), series.index.max(), freq="M")
    series = series.reindex(full)  # missing months in the middle become NaN
    if series.notna().sum() < MIN_VALID_MONTHS:
        raise SeriesError(f"{path}: not enough data ({series.notna().sum()} valid months, "
                          f"need {MIN_VALID_MONTHS})")
    return ([str(m) for m in series.index],
            [None if pd.isna(v) else round(float(v), 4) for v in series])
