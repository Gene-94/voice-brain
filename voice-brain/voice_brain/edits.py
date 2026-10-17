"""Last-action ledger: powers \"scratch that\" / \"fix that\" undo-by-voice.

Every daemon write records prior state (base64 content or None for creations).
Undo reverses the most recent action only if the file hasn't been edited since
(sha256 check) — we never clobber user edits.
"""

from __future__ import annotations

import base64
import binascii
import json
import time
from dataclasses import dataclass, field
from pathlib import Path

from .vault import sha256_text


@dataclass
class FileOp:
    rel: str
    op: str                    # "create" | "modify"
    prior_b64: str | None = None
    after_sha: str = ""


@dataclass
class Action:
    ts: float
    description: str
    ops: list[FileOp] = field(default_factory=list)


class LedgerError(RuntimeError):
    pass


def _encode(text: str | None) -> str | None:
    if text is None:
        return None
    return base64.b64encode(text.encode("utf-8")).decode("ascii")


def _decode(b64: str | None) -> str | None:
    if b64 is None:
        return None
    try:
        return base64.b64decode(b64).decode("utf-8")
    except (binascii.Error, UnicodeDecodeError):
        return None


class ActionLedger:
    def __init__(self, cfg, vault):
        self.cfg = cfg
        self.vault = vault
        self.file: Path = cfg.state_dir() / "ledger.json"
        self.max_actions = int(cfg.get("editing.undo_depth", 10))

    # ------------------------------------------------------------------ persistence

    def _load(self) -> list[Action]:
        if not self.file.exists():
            return []
        try:
            raw = json.loads(self.file.read_text())
            return [Action(ts=a["ts"], description=a["description"],
                           ops=[FileOp(**op) for op in a["ops"]]) for a in raw]
        except (json.JSONDecodeError, KeyError, TypeError):
            return []

    def _save(self, actions: list[Action]) -> None:
        self.file.parent.mkdir(parents=True, exist_ok=True)
        self.file.write_text(json.dumps([
            {"ts": a.ts, "description": a.description,
             "ops": [vars(op) | {} for op in a.ops]} for a in actions
        ], indent=1))

    # ------------------------------------------------------------------ record / undo

    def record(self, description: str, ops: list[tuple[Path, str | None]]) -> None:
        """`ops`: (path, prior_text). prior_text None => creation.
        Called AFTER the write succeeded; we hash the new content for undo safety."""
        built: list[FileOp] = []
        for path, prior in ops:
            rel = path.relative_to(self.vault.root).as_posix()
            current = path.read_text() if path.exists() else ""
            built.append(FileOp(rel=rel,
                                 op="create" if prior is None else "modify",
                                 prior_b64=_encode(prior),
                                 after_sha=sha256_text(current)))
        actions = self._load()
        actions.append(Action(ts=time.time(), description=description, ops=built))
        self._save(actions[-self.max_actions:])

    def last(self) -> Action | None:
        actions = self._load()
        return actions[-1] if actions else None

    def undo_last(self) -> str:
        """Reverse the last action. Raises if edited since or nothing to undo."""
        actions = self._load()
        if not actions:
            raise LedgerError("Nothing to undo.")
        action = actions.pop()
        undone: list[str] = []
        skipped: list[str] = []
        for op in reversed(action.ops):
            path = self.vault.root / op.rel
            current = path.read_text() if path.exists() else ""
            if sha256_text(current) != op.after_sha:
                skipped.append(f"{op.rel} (edited since — left alone)")
                continue
            if op.op == "create":
                path.unlink(missing_ok=True)
                undone.append(f"deleted {op.rel}")
            else:
                prior = _decode(op.prior_b64)
                if prior is None:
                    skipped.append(f"{op.rel} (prior content unrecoverable)")
                    continue
                self.vault.write_atomic(path, prior)
                undone.append(f"restored {op.rel}")
        self._save(actions)
        parts = undone + skipped
        return f"Undid: {action.description}. " + "; ".join(parts) if parts else \
               f"Undid: {action.description}."
