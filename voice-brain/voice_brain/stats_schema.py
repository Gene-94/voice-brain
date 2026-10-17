"""Voice Brain Stats Schema v1.0.0 — pure-Python validation.

Design (plan §6.3): flat derived scores for charting, `_scale`/`_estimate` flags for
honesty, `source` + `notes` required per category. Returns a list of human-readable
errors for the LLM repair loop.
"""

from __future__ import annotations

CATEGORIES = ["sleep", "mood", "energy", "physical", "nutrition", "cognitive",
              "creative_output", "social", "environment", "habits", "time_use"]

SCALE_100 = ("readiness_score", "quality_score", "creativity_score", "focus_score",
             "productivity_score", "dietary_quality_score", "completeness_score")
SCALE_10 = ("subjective_rating", "average_score", "fatigue_level", "anxiety_level",
            "depression_screen", "mental_clarity", "wellbeing_index", "novelty_average",
            "depth_average", "connectivity_average", "clarity_average",
            "actionability_average", "loneliness_score", "perceived_exertion",
            "sleep_hygiene_score")


def validate_stats(doc: object) -> list[str]:
    if not isinstance(doc, dict):
        return ["top-level must be a JSON object"]
    errors: list[str] = []

    for key in ("date", "generated_at", "derived", "insights"):
        if key not in doc:
            errors.append(f"missing required top-level key '{key}'")

    if "date" in doc:
        date = str(doc["date"])
        if len(date) != 10 or date[4] != "-" or date[7] != "-":
            errors.append("'date' must be YYYY-MM-DD")

    for cat in CATEGORIES:
        node = doc.get(cat)
        if not isinstance(node, dict):
            errors.append(f"category '{cat}' missing or not an object")
            continue
        if "notes" not in node:
            errors.append(f"{cat}.notes is required (1-3 sentences)")
        if "source" not in node:
            errors.append(f"{cat}.source is required (traceability)")

    def check_scales(node, prefix=""):
        if not isinstance(node, dict):
            return
        for key, val in node.items():
            if not isinstance(val, (int, float)) or isinstance(val, bool):
                continue
            if key in SCALE_100 and not (0 <= val <= 100):
                errors.append(f"{prefix}{key}={val} must be 0-100")
            if key in SCALE_10 and not (0 <= val <= 10):
                errors.append(f"{prefix}{key}={val} must be 0-10")

    for cat in CATEGORIES + ["derived", "insights"]:
        if isinstance(doc.get(cat), dict):
            check_scales(doc[cat], prefix=f"{cat}.")

    derived = doc.get("derived")
    if isinstance(derived, dict):
        if "readiness_score" not in derived:
            errors.append("derived.readiness_score is required (0-100)")
        if "recommendations" not in derived:
            errors.append("derived.recommendations is required (list)")
        recs = derived.get("recommendations")
        if isinstance(recs, list) and not recs:
            errors.append("derived.recommendations must not be empty — cite at least one "
                          "evidence-based action, or explain why none apply")
    insights = doc.get("insights")
    if isinstance(insights, dict) and not str(insights.get("narrative", "")).strip():
        errors.append("insights.narrative is required (2-3 sentence human story)")

    return errors
