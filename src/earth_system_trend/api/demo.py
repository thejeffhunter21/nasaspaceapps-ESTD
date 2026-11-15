"""J13: ready-made demo stories for the dashboard's demo buttons (Phoenix).

Picked from the real regions by code, so the numbers always match /trend:
the whole study area, the fastest-warming part and the slowest-warming part.
"""

from __future__ import annotations

from ..contract import Results


def pick_stories(regions: list[Results]) -> list[dict]:
    """Up to three stories, each naming a region_id the other endpoints accept."""
    if not regions:
        return []
    main, parts = regions[0], regions[1:]
    stories = [_story(main, "whole_area", f"The whole {main.region}",
                      f"Start here: the full {main.period.start} to {main.period.end} record "
                      "for the whole area.")]
    if len(parts) >= 2:
        fastest = max(parts, key=lambda r: r.trend.slope)
        slowest = min(parts, key=lambda r: r.trend.slope)
        if fastest.region_id != slowest.region_id:
            stories.append(_story(fastest, "fastest", "Fastest change",
                                  "The part of the area changing the most."))
            stories.append(_story(slowest, "slowest", "Slowest change",
                                  "Same city, a different rate: the part changing the least."))
    return stories


def _story(r: Results, story_id: str, label: str, intro: str) -> dict:
    per_year = r.trend.slope * 12
    unit = r.units
    sig = "significant" if r.trend.p < 0.05 else "not significant"
    p_text = "p < 0.001" if r.trend.p < 0.001 else f"p = {r.trend.p:.3g}"
    return {
        "id": story_id,
        "label": label,
        "description": f"{intro} {r.region}: {r.trend.trend}, about {per_year:+.3g} {unit} "
                       f"per year ({sig}, {p_text}).",
        "region_id": r.region_id,
        "region": r.region,
        "trend": r.trend.model_dump(),
    }
