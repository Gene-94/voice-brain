"""Daily Journal router: \"log this: ...\" -> timestamped append to Journal/YYYY-MM-DD.md.

Implicit stat capture: a quick LLM pass extracts structured tags (mood=8, food:eggs, ...)
embedded as invisible HTML comments — never ruining the reading view, fully usable by
the stats generator.
"""

from __future__ import annotations

from datetime import date as Date, datetime
from pathlib import Path

from .prompts import PROMPT_VERSIONS, journal_enrich
from .vault import render_frontmatter

DAILY_TEMPLATE = """---
date: "{date}"
created_by: voice-brain
entry_count: 0
prompt_version: "{prompt_version}"
---

# Journal — {pretty_date}
"""


def _validate_enrich(doc: object) -> list[str]:
    if not isinstance(doc, dict) or "heading" not in doc or "tags" not in doc:
        return ["must contain 'heading' and 'tags'"]
    if not isinstance(doc["tags"], list):
        return ["'tags' must be a list"]
    return []


class JournalRouter:
    def __init__(self, cfg, vault, llm, ledger):
        self.cfg = cfg
        self.vault = vault
        self.llm = llm
        self.ledger = ledger

    def handle(self, entry_text: str, now: datetime | None = None) -> Path:
        now = now or datetime.now()
        day: Date = now.date()
        path = self.vault.journal_path(day)

        heading, tags = self._enrich(entry_text)

        if not path.exists():
            content = DAILY_TEMPLATE.format(
                date=day.isoformat(),
                pretty_date=day.strftime("%A, %B %d, %Y"),
                prompt_version=PROMPT_VERSIONS["journal_enrich"],
            )
            self.vault.write_atomic(path, content)

        prior = path.read_text()
        entry = self._render_entry(now, heading, tags, entry_text)
        self.vault.write_atomic(path, prior.rstrip("\n") + "\n\n" + entry)
        self._bump_entry_count(path)

        self.ledger.record(f"journal entry: {heading or 'log'}", [(path, prior)])
        return path

    # ------------------------------------------------------------------ internals

    def _enrich(self, text: str) -> tuple[str, list[str]]:
        try:
            doc = self.llm.generate(journal_enrich(text), lane="quick",
                                    json_mode=True, validator=_validate_enrich)
            heading = str(doc.get("heading", "")).strip()[:60] or "Log"
            tags = [str(t) for t in doc.get("tags", []) if t][:8]
            return heading, tags
        except Exception:
            # Enrichment is optional sugar — never block the journal write.
            return "Log", []

    def _render_entry(self, now: datetime, heading: str, tags: list[str], text: str) -> str:
        parts = [f"## {now.strftime('%H:%M')} — {heading}", "", text.strip()]
        if tags:
            parts += ["", f"<!--vb: {' '.join(tags)} -->"]
        parts += ["", "---"]
        return "\n".join(parts)

    def _bump_entry_count(self, path: Path) -> None:
        from .vault import parse_frontmatter
        text = path.read_text()
        fm, body = parse_frontmatter(text)
        try:
            fm["entry_count"] = int(fm.get("entry_count", 0)) + 1
        except (TypeError, ValueError):
            fm["entry_count"] = 1
        if body.startswith("\n"):
            body = body[1:]
        self.vault.write_atomic(path, render_frontmatter(fm) + body)
