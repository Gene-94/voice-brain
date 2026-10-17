"""Trigger routing: phrase prefixes -> routers, with priority rules from the spec."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum


class Kind(Enum):
    DREAM = "dream"
    STATS = "stats"
    BRIEF = "brief"
    STAT_LOG = "stat_log"
    JOURNAL = "journal"
    NOTE = "note"          # user pattern: polished note, optional custom folder
    CAPTURE = "capture"    # user pattern: verbatim capture safety net
    SCRATCH = "scratch"
    DICTATION = "dictation"
    GENERAL = "general"

ROUTE_TO_KIND = {
    "dream": Kind.DREAM,
    "journal": Kind.JOURNAL,
    "note": Kind.NOTE,
    "capture": Kind.CAPTURE,
    "query": Kind.GENERAL,   # query routes through the general classifier to the Q&A engine
    "stats": Kind.STATS,
    "brief": Kind.BRIEF,
    "scratch": Kind.SCRATCH,
}


# Order matters — priority rule: dream prefix wins over journal if both appear
# ("log this: I had a dream..." routes to Dream Journal).
TRIGGERS: list[tuple[Kind, re.Pattern]] = [
    (Kind.DREAM, re.compile(
        r"^\s*(?:(?:last\s+night\s+)?i\s+(?:just\s+)?(?:had\s+a\s+dream|dream(?:ed|t))"
        r"|in\s+my\s+dream"
        r"|there\s+was\s+this\s+dream"
        r"|tinha\s+um\s+sonho"
        r"|sonhei\s+que)\b", re.IGNORECASE)),
    (Kind.SCRATCH, re.compile(r"^\s*(scratch\s+that|undo\s+(?:that|last)|forget\s+that)\b", re.IGNORECASE)),
    (Kind.STATS, re.compile(
        r"^\s*(?:generate|make|create)\s+stats?\b|^\s*how\s+was\s+my\s+day\b|^\s*analyze\s+my\s+week\b",
        re.IGNORECASE)),
    (Kind.BRIEF, re.compile(r"^\s*brief\s+me\b|^\s*what.?s\s+my\s+(?:status|readiness)\b", re.IGNORECASE)),
    (Kind.STAT_LOG, re.compile(r"^\s*(?:log|track)\s+(?:a\s+)?stat\b", re.IGNORECASE)),
    (Kind.JOURNAL, re.compile(
        r"^\s*(?:log\s+(?:this|that)|journal\s+this|remember\s+this|anota\s+(?:isso|aquilo))\b",
        re.IGNORECASE)),
    (Kind.DICTATION, re.compile(r"^\s*(?:start|begin)\s+dictation\b|^\s*dicta(?:tion)?\s+mode\b", re.IGNORECASE)),
]


@dataclass
class Intent:
    kind: Kind
    text: str
    payload: str = field(default_factory=str)
    folder: str | None = None   # user-pattern target folder for NOTE routes


def classify(text: str, cfg=None, patterns=None) -> Intent:
    """User patterns (vault file) first — they override the built-ins — then the
    built-in regex triggers. Unmatched -> GENERAL (LLM classifier downstream)."""
    clean = text.strip()
    if not clean:
        return Intent(Kind.GENERAL, clean)

    if patterns is not None:
        hit = patterns.match(clean)
        if hit:
            rule, m = hit
            return Intent(kind=ROUTE_TO_KIND.get(rule.route, Kind.GENERAL), text=clean,
                          payload=clean[m.end():].lstrip(" :,-"), folder=rule.folder)

    if cfg is not None and not cfg.get("triggers.dream", True):
        triggers = [t for t in TRIGGERS if t[0] is not Kind.DREAM]
    else:
        triggers = TRIGGERS

    for kind, pattern in triggers:
        match = pattern.match(clean)
        if match:
            return Intent(kind=kind, text=clean, payload=clean[match.end():].lstrip(" :,-"))

    return Intent(kind=Kind.GENERAL, text=clean, payload=clean)


def strip_trigger(intent: Intent) -> str:
    """The utterance minus the trigger phrase (for journal/dream narration etc.)."""
    return intent.payload or intent.text
