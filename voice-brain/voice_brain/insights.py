"""Deterministic insights engine. The LLM narrates; this module calculates.

Pearson correlations, trend deltas, streaks, the C/C (consume/create) ratio and
anomaly z-scores are computed from Stats/*.json history in pure Python. LLMs are
handed these numbers pre-computed — they may interpret, never invent, statistics.
"""

from __future__ import annotations

import math
from datetime import date as Date, timedelta


def pearson(xs: list[float], ys: list[float]) -> float | None:
    n = len(xs)
    if n < 3:
        return None
    mx, my = sum(xs) / n, sum(ys) / n
    dx = [x - mx for x in xs]
    dy = [y - my for y in ys]
    num = sum(a * b for a, b in zip(dx, dy))
    den = math.sqrt(sum(a * a for a in dx) * sum(b * b for b in dy))
    if den == 0:
        return None
    return round(num / den, 2)


def zscore(value: float, series: list[float]) -> float | None:
    if len(series) < 3:
        return None
    mean = sum(series) / len(series)
    var = sum((x - mean) ** 2 for x in series) / len(series)
    sd = var ** 0.5
    if sd == 0:
        return None
    return round((value - mean) / sd, 2)


def _series(stats: list[dict], dotted: str) -> list[float]:
    """Extract e.g. 'derived.readiness_score' or 'sleep.subjective_rating' across days."""
    out: list[float] = []
    for doc in stats:
        node: object = doc
        for part in dotted.split("."):
            if not isinstance(node, dict):
                node = None
                break
            node = node.get(part)
        if isinstance(node, (int, float)):
            out.append(float(node))
    return out


def _extract(doc: dict, dotted: str) -> float | None:
    node: object = doc
    for part in dotted.split("."):
        if not isinstance(node, dict):
            return None
        node = node.get(part)
    return float(node) if isinstance(node, (int, float)) else None


CORRELATION_PAIRS = [
    ("sleep.quality_score", "derived.wellbeing_index", "sleep quality", "wellbeing"),
    ("sleep.quality_score", "creative_output.creativity_score", "sleep quality", "creativity"),
    ("physical.exercise.did_exercise", "mood.average_score", "exercise", "mood"),
    ("nutrition.caffeine_mg_estimate", "energy.afternoon", "caffeine", "afternoon energy"),
]


def compute_correlations(history: list[dict], min_days: int = 5) -> list[dict]:
    """Correlations with honest n — only reported when there's actual evidence."""
    out = []
    n_days = len(history)
    for a, b, label_a, label_b in CORRELATION_PAIRS:
        xs, ys = [], []
        for doc in history:
            va, vb = _extract(doc, a), _extract(doc, b)
            if va is not None and vb is not None:
                xs.append(va)
                ys.append(vb)
        if len(xs) >= min_days:
            r = pearson(xs, ys)
            if r is not None and abs(r) >= 0.3:
                out.append({
                    "factor_a": label_a,
                    "factor_b": label_b,
                    "relationship": "positive" if r > 0 else "negative",
                    "strength": r,
                    "n_day_support": len(xs),
                    "notes": f"Deterministic Pearson r over {len(xs)} days.",
                })
    return out


def compute_trend(today: dict | None, history: list[dict]) -> dict:
    ys = [h["derived"]["readiness_score"] for h in history
          if isinstance(h.get("derived"), dict)
          and isinstance(h["derived"].get("readiness_score"), (int, float))]
    todays_score = _extract(today or {}, "derived.readiness_score")
    out: dict = {"trending": "unknown", "trend_explanation": "Not enough history yet."}
    if len(ys) >= 2 and todays_score is not None:
        prev = ys[-1]
        delta = round(todays_score - prev)
        if abs(delta) < 5:
            out["trending"] = "stable"
            out["trend_explanation"] = f"Readiness stable vs yesterday ({prev})."
        else:
            out["trending"] = f"{'up' if delta > 0 else 'down'}_{abs(delta)}pts"
            out["trend_explanation"] = (
                f"Readiness {'up' if delta > 0 else 'down'} {abs(delta)} pts vs yesterday ({prev}).")
    z = zscore(todays_score, ys) if todays_score is not None else None
    if z is not None and abs(z) >= 2:
        out["anomaly_flag"] = f"Readiness is a {z}σ outlier vs your recent baseline."
    return out


def cc_ratio(journal_words: int, creative_words: int) -> dict:
    """Consume/Create ratio from the spec (§H): journal+dream words vs produced words."""
    consumed = journal_words
    created = creative_words
    ratio = round(consumed / created, 2) if created else None
    return {
        "consumed_words": consumed,
        "created_words": created,
        "cc_ratio": ratio,
        "cc_ratio_note": ("Healthy ~1:1. You are logging more than producing."
                          if ratio and ratio > 2 else None),
    }


def capture_streak(stats_history: list[dict], journal_days: set[Date],
                   today: Date) -> int:
    days = set()
    for doc in stats_history:
        if doc.get("date"):
            try:
                days.add(Date.fromisoformat(doc["date"]))
            except ValueError:
                pass
    days |= journal_days
    streak = 0
    day = today
    while day in days:
        streak += 1
        day -= timedelta(days=1)
    return streak


def precompute_block(today: dict | None, history: list[dict],
                     journal_words: int, creative_words: int,
                     journal_days: set[Date], today_date: Date,
                     min_days: int = 5) -> dict:
    """Everything handed to the LLM as authoritative numbers."""
    return {
        "correlations": compute_correlations(history, min_days=min_days),
        "trend": compute_trend(today, history),
        "cc_ratio": cc_ratio(journal_words, creative_words),
        "capture_streak_days": capture_streak(history, journal_days, today_date),
        "rule": "Use these numbers exactly. Do not recompute or invent statistics.",
    }
