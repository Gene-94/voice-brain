"""General note handling: LLM-drafted notes and the capture-everything safety net.

Nothing you say is ever lost: if intent classification fails or the LLM errors,
the utterance lands verbatim in the Voice Brain Inbox.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from .prompts import PROMPT_VERSIONS, note_draft, polish_note
from .vault import render_frontmatter, slugify


def save_raw_transcript(vault, cfg, text: str, source: str, route: str,
                         confidence: float | None, now: datetime | None = None) -> str:
    """Every utterance lands here VERBATIM before any LLM runs — the raw whisper
    transcript, filed in the Voice Brain Inbox. Not in the undo ledger: your words
    survive LLM failures and 'scratch that'. The structured output goes to its own
    route folder; this is the immutable source of truth."""
    now = now or datetime.now()
    fm = render_frontmatter({
        "title": f"Transcript {now.strftime('%H:%M')}",
        "tags": ["transcript"],
        "created_at": now.isoformat(timespec="seconds"),
        "created_by": "voice-brain",
        "source": source,
        "route": route,
        "confidence": confidence,
    })
    stamp = now.strftime("%H%M%S")
    rel = (f"{cfg.folder('inbox')}/{now.date().isoformat()}"
           f"_transcript-{stamp}.md")
    vault.write_note(rel, fm + f"\n# Transcript {now.strftime('%H:%M')}\n\n{text.strip()}\n")
    return rel

NOTE_TEMPLATE = """---
title: "{title}"
tags: {tags}
created_at: "{created}"
created_by: voice-brain
prompt_version: "{prompt_version}"
---

# {title}

{content}
"""


def _validate_note(doc: object) -> list[str]:
    if not isinstance(doc, dict):
        return ["must be an object"]
    if not str(doc.get("title", "")).strip():
        return ["'title' is required"]
    if not str(doc.get("content", "")).strip():
        return ["'content' is required"]
    return []


class NoteWriter:
    def __init__(self, cfg, vault, llm, ledger):
        self.cfg = cfg
        self.vault = vault
        self.llm = llm
        self.ledger = ledger

    def create(self, spoken_intent: str, now: datetime | None = None) -> str:
        """LLM-drafted note -> Voice Brain Inbox. Returns rel path."""
        now = now or datetime.now()
        doc = self.llm.generate(note_draft(spoken_intent), lane="quick",
                                json_mode=True, validator=_validate_note)
        title = str(doc["title"]).strip()
        tags = [str(t).lstrip("#").lower() for t in (doc.get("tags") or []) if t][:4]
        content = str(doc["content"]).strip()

        note = NOTE_TEMPLATE.format(
            title=title.replace('"', "'"),
            tags=str(tags).replace("'", '"'),
            created=now.isoformat(timespec="seconds"),
            prompt_version=PROMPT_VERSIONS["note_draft"],
            content=content,
        )
        rel = (f"{self.cfg.folder('inbox')}/{now.date().isoformat()}_"
               f"{slugify(title, max_words=6)}.md")
        path = self.vault.write_note(rel, note)
        self.ledger.record(f"note created: {title}", [(path, None)])
        return path.relative_to(self.vault.root).as_posix()

    def create_polished(self, raw_text: str, folder: str | None = None,
                         now: datetime | None = None) -> str:
        """Raw transcript -> Gemma formats (bullets, structure) -> clean note.
        The raw transcript is preserved at the bottom — never lose input."""
        now = now or datetime.now()
        doc = self.llm.generate(polish_note(raw_text), lane="quick",
                                json_mode=True, validator=_validate_note)
        title = str(doc["title"]).strip()
        tags = [str(t).lstrip("#").lower() for t in (doc.get("tags") or []) if t][:4]
        content = str(doc["content"]).strip()

        dest = folder or self.cfg.folder("inbox")
        fm = render_frontmatter({
            "title": title,
            "tags": tags or ["capture"],
            "created_at": now.isoformat(timespec="seconds"),
            "created_by": "voice-brain",
            "prompt_version": PROMPT_VERSIONS["polish_note"],
        })
        body = f"# {title}\n\n{content}\n"
        rel = f"{dest}/{now.date().isoformat()}_{slugify(title, max_words=6)}.md"
        path = self.vault.write_note(rel, fm + body)
        self.ledger.record(f"polished note: {title}", [(path, None)])
        return path.relative_to(self.vault.root).as_posix()

    def capture(self, raw_text: str, now: datetime | None = None) -> str:
        """Verbatim fallback capture. Never calls the LLM — this is the safety net."""
        now = now or datetime.now()
        fm = render_frontmatter({
            "title": f"Capture {now.strftime('%H:%M')}",
            "tags": ["capture"],
            "created_at": now.isoformat(timespec="seconds"),
            "created_by": "voice-brain",
        })
        rel = (f"{self.cfg.folder('inbox')}/{now.date().isoformat()}_"
               f"capture-{now.strftime('%H%M%S')}.md")
        path = self.vault.write_note(rel, fm + f"\n# Capture {now.strftime('%H:%M')}\n\n{raw_text.strip()}\n")
        self.ledger.record("verbatim capture", [(path, None)])
        return path.relative_to(self.vault.root).as_posix()
