"""Vault organization: dry-run by default, plan files applied explicitly.

Destructive ops can never be triggered by voice alone — a plan must be generated,
reviewed, and applied with `voice-brain apply-plan <file>`.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from .prompts import organize_plan

ALLOWED_FOLDERS = ["Inbox", "Projects", "Areas", "Resources", "Archive"]
MIN_CONFIDENCE = 0.7  # spec default; plans below this don't even get proposed


def _validate_plan(doc: object) -> list[str]:
    if not isinstance(doc, dict) or "actions" not in doc:
        return ["must contain 'actions' list"]
    errors: list[str] = []
    for i, a in enumerate(doc.get("actions", [])):
        if not isinstance(a, dict) or a.get("action") not in ("move", "tag"):
            errors.append(f"actions[{i}].action must be 'move' or 'tag'")
            continue
        if not a.get("from"):
            errors.append(f"actions[{i}].from missing")
        if a["action"] == "move":
            to = str(a.get("to", ""))
            if not any(to.startswith(f + "/") for f in ALLOWED_FOLDERS):
                errors.append(f"actions[{i}].to '{to}' not under allowed folders")
    return errors


class Organizer:
    def __init__(self, cfg, vault, llm, ledger):
        self.cfg = cfg
        self.vault = vault
        self.llm = llm
        self.ledger = ledger

    def plan(self) -> Path:
        inbox = self.cfg.folder("inbox")
        notes = [n for n in self.vault.index()
                 if n.rel.startswith(inbox + "/") and not self.vault.is_ignored(n.rel)]
        if not notes:
            raise RuntimeError("Inbox is empty — nothing to organize.")
        blocks = []
        for note in notes[:15]:
            blocks.append(f"[{note.rel}]\n{note.body[:400].strip()}")
        doc = self.llm.generate(organize_plan("\n\n".join(blocks)), lane="deep",
                                json_mode=True, validator=_validate_plan)

        plans_dir = self.cfg.state_dir() / "plans"
        plans_dir.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y%m%d-%H%M%S")
        plan_path = plans_dir / f"plan-{stamp}.json"
        plan_path.write_text(json.dumps(doc, indent=1))

        md = self.render_plan_md(doc)
        (plans_dir / f"plan-{stamp}.md").write_text(md)
        return plan_path

    def render_plan_md(self, doc: dict) -> str:
        lines = ["# Organize Plan", "", "Apply with: `voice-brain apply-plan <file.json`", ""]
        for a in doc.get("actions", []):
            if a.get("action") == "move":
                lines.append(f"- **move** `{a.get('from')}` → `{a.get('to')}` — {a.get('reason', '')}")
            elif a.get("action") == "tag":
                lines.append(f"- **tag** `{a.get('from')}` + {a.get('tags')} — {a.get('reason', '')}")
        return "\n".join(lines) + "\n"

    def apply(self, plan_file: Path) -> list[str]:
        doc = json.loads(Path(plan_file).read_text())
        _validate_plan(doc)  # raises nothing; sanity re-check on disk file
        self.vault.git_snapshot("voice-brain: pre-organize snapshot")

        applied: list[str] = []
        ops_for_ledger: list[tuple[Path, str | None]] = []
        for a in doc.get("actions", []):
            note = self.vault.find(str(a.get("from", "")))
            if note is None:
                applied.append(f"SKIP (missing): {a.get('from')}")
                continue
            if a.get("action") == "move":
                dest = self.vault.root / str(a.get("to", "")).lstrip("/")
                dest.parent.mkdir(parents=True, exist_ok=True)
                prior = note.text
                note.path.rename(dest)
                ops_for_ledger.append((note.path, None))
                ops_for_ledger.append((dest, None))
                applied.append(f"moved: {note.rel} -> {a.get('to')}")
            elif a.get("action") == "tag":
                from .vault import parse_frontmatter, render_frontmatter
                prior = note.text
                fm, body = parse_frontmatter(prior)
                fm["tags"] = list(dict.fromkeys(
                    [str(t).lstrip("#") for t in fm.get("tags", [])] +
                    [str(t).lstrip("#") for t in a.get("tags", [])]))
                self.vault.write_atomic(note.path, render_frontmatter(fm) + body)
                ops_for_ledger.append((note.path, prior))
                applied.append(f"tagged: {note.rel} + {a.get('tags')}")
        self.ledger.record("organize plan applied", ops_for_ledger)
        return applied
