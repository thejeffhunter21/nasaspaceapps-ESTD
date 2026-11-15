"""Save the AI Climate Detective's guided investigations for the web explorer.

Runs the AI layer's own code (app/climate_detective.py: interpret_question, load_evidence,
investigate) for each suggested question and writes the exact findings, evidence rows and chart
series to web/data/detective.json. Nothing is re-derived here, and Gemini is not used.
tests/web/test_detective_json.py fails if the committed file drifts from what the code produces.

  uv run --locked python scripts/build_detective_json.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "web/data/detective.json"


def build() -> dict:
    sys.path.insert(0, str(ROOT / "app"))
    import climate_detective as cd

    evidence = cd.load_evidence()
    investigations = []
    for label, question in cd.QUESTIONS.items():
        intent = cd.interpret_question(question)
        figure, finding, rows = cd.investigate(intent, evidence)
        fig = json.loads(figure.to_json())
        layout = fig.get("layout", {})
        # Subplot titles are annotations too; skip the shared source note at the bottom.
        subplot_titles = [a["text"] for a in layout.get("annotations", [])
                          if not a.get("text", "").startswith("NASA")]
        investigations.append({
            "label": label,
            "question": question,
            "intent": intent,
            "title": layout.get("title", {}).get("text", ""),
            "finding": finding,
            "rows": rows,
            "x_title": (layout.get("xaxis", {}).get("title") or {}).get("text", ""),
            "y_title": (layout.get("yaxis", {}).get("title") or {}).get("text", ""),
            "subplot_titles": subplot_titles if intent == "acceleration" else [],
            "traces": [{"type": t.get("type", "scatter"), "name": t.get("name", ""),
                        "x": t.get("x", []), "y": t.get("y", []),
                        "panel": 2 if t.get("xaxis") == "x2" else 1} for t in fig["data"]],
        })
    return {
        "generated_by": "scripts/build_detective_json.py from app/climate_detective.py",
        "mode": "Guided Investigation Demo: predefined workflows, local approved NASA results, "
                "deterministic explanations. Gemini is not used.",
        "source": evidence["phoenix_study_area"]["source"],
        "limits": cd.LIMITS,
        "unsupported_message": (
            "This demonstration supports regional warming comparisons, historical trend analysis, "
            "and selected hypothesis investigations. Try a suggested question. Only Phoenix, "
            "2003–2024 is supported. Hottest is different from fastest warming."),
        "method_note": (
            "Ranking and comparison use stored seasonal Mann–Kendall / seasonal Sen's slope results. "
            "Monthly slopes are multiplied by 12 for °C/year. Evidence Challenger recomputes this "
            "same validated method on two January-aligned periods; it does not test acceleration. "
            "Missing observations remain gaps."),
        "investigations": investigations,
    }


def main() -> int:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(build(), ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
