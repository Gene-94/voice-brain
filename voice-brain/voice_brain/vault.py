"""Vault layer: index, atomic writes, frontmatter, search, journal helpers.

Safety rules (see plan §5.3 / §13):
- all writes atomic (tmpfile + os.replace) — Obsidian never sees a torn file
- destructive ops live in organize.py and require an explicitly applied plan
- `.voice-brain-ignore` honored everywhere
"""

from __future__ import annotations

import hashlib
import os
import re
import threading
import time
from dataclasses import dataclass, field
from datetime import date as Date, datetime
from pathlib import Path
from typing import Iterable

import yaml

FRONT_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*\n?", re.DOTALL)
WIKILINK_RE = re.compile(r"\[\[([^\]|#]+)(?:[|#][^\]]*)?\]\]")
TAG_RE = re.compile(r"(?<![\w/])#([a-zA-Z0-9_/\-]+)")
TODO_RE = re.compile(r"^\s*- \[ \] ", re.MULTILINE)

FRONT_DELIM = "---"
GENERATED_MARKER = ".voice-brain-generated"
MARKER_TEXT = (
    "# Voice Brain managed folder\n\n"
    "This folder is managed by Voice Brain. Files here are created/updated by voice.\n"
    "You can edit them freely — Voice Brain appends, never clobbers.\n"
)


def slugify(text: str, max_words: int = 8) -> str:
    words = re.sub(r"[^\w\s\-]", "", text).split()
    words = [w for w in words if w][:max_words]
    return "_".join(words) or "untitled"


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def parse_frontmatter(text: str) -> tuple[dict, str]:
    match = FRONT_RE.match(text)
    if not match:
        return {}, text
    raw, body = match.group(1), text[match.end():]
    try:
        fm = yaml.safe_load(raw) or {}
        if not isinstance(fm, dict):
            fm = {}
    except yaml.YAMLError:
        fm = {}
    return fm, body


def render_frontmatter(fm: dict) -> str:
    return f"{FRONT_DELIM}\n{yaml.safe_dump(fm, sort_keys=False, allow_unicode=True).strip()}\n{FRONT_DELIM}\n"


@dataclass
class Note:
    path: Path
    rel: str
    mtime: float
    frontmatter: dict = field(default_factory=dict)
    body: str = ""
    text: str = ""
    wikilinks: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    words: int = 0
    open_todos: int = 0

    @property
    def title(self) -> str:
        if self.frontmatter.get("title"):
            return str(self.frontmatter["title"])
        if self.body.lstrip().startswith("# "):
            return self.body.lstrip()[2:].splitlines()[0].strip()
        return self.path.stem

    @property
    def created_on(self) -> Date | None:
        ts = self.frontmatter.get("created_at") or self.frontmatter.get("recorded_at")
        if ts:
            try:
                return datetime.fromisoformat(str(ts)).date()
            except ValueError:
                pass
        # fall back to first-line date in filename YYYY-MM-DD
        m = re.match(r"(\d{4}-\d{2}-\d{2})", self.path.stem)
        if m:
            try:
                return Date.fromisoformat(m.group(1))
            except ValueError:
                pass
        return None


class Vault:
    def __init__(self, cfg):
        self.cfg = cfg
        self.root: Path = cfg.vault_root().expanduser()
        self._index: list[Note] = []
        self._indexed_at: float = 0.0
        self._lock = threading.RLock()

    # ------------------------------------------------------------ bootstrap

    def ensure_folders(self) -> list[Path]:
        created: list[Path] = []
        for key in ("dream", "journal", "stats", "inbox"):
            folder = self.root / self.cfg.folder(key)
            if not folder.exists():
                folder.mkdir(parents=True, exist_ok=True)
                (folder / GENERATED_MARKER).write_text(MARKER_TEXT)
                created.append(folder)
        return created

    def special_rel_paths(self) -> set[str]:
        return {self.cfg.folder(k) for k in ("dream", "journal", "stats")}

    # ------------------------------------------------------------ ignore

    def _ignore_patterns(self) -> list[str]:
        ignore_file = self.root / self.cfg.get("vault.ignore_file", ".voice-brain-ignore")
        if not ignore_file.exists():
            return []
        pats = [ln.strip() for ln in ignore_file.read_text().splitlines()
                if ln.strip() and not ln.strip().startswith("#")]
        return pats

    def is_ignored(self, rel_path: str) -> bool:
        rel = rel_path.replace(os.sep, "/")
        for pat in self._ignore_patterns():
            if rel.startswith(pat.rstrip("/")) or rel == pat:
                return True
        return False

    # ------------------------------------------------------------ index

    def index(self, rebuild: bool = False) -> list[Note]:
        with self._lock:
            if self._index and not rebuild and time.time() - self._indexed_at < 30:
                return self._index
            notes: list[Note] = []
            for path in self.root.rglob("*.md"):
                rel = path.relative_to(self.root).as_posix()
                if self.is_ignored(rel) or path.name.startswith("."):
                    continue
                try:
                    text = path.read_text(errors="replace")
                except OSError:
                    continue
                fm, body = parse_frontmatter(text)
                notes.append(Note(
                    path=path, rel=rel, mtime=path.stat().st_mtime,
                    frontmatter=fm, body=body, text=text,
                    wikilinks=sorted({m.group(1).strip() for m in WIKILINK_RE.finditer(text)}),
                    tags=[t for t in TAG_RE.findall(body)[:20]],
                    words=len(body.split()),
                    open_todos=len(TODO_RE.findall(body)),
                ))
            self._index = notes
            self._indexed_at = time.time()
            return notes

    def find(self, rel: str) -> Note | None:
        rel = rel.replace(os.sep, "/")
        for note in self.index():
            if note.rel == rel or note.path.name == rel or note.path.stem == rel:
                return note
        return None

    # ------------------------------------------------------------ search (TF, no vector DB)

    def search(self, query: str, k: int = 6) -> list[Note]:
        terms = [t.lower() for t in re.findall(r"\w+", query) if len(t) > 2]
        if not terms:
            return []
        scored: list[tuple[float, Note]] = []
        for note in self.index():
            title = note.title.lower()
            body = note.body.lower()
            score = 0.0
            for term in terms:
                score += 3.0 * title.count(term) + 1.0 * body.count(term)
                if term in (t.lower() for t in note.tags):
                    score += 2.0
            if score > 0:
                scored.append((score, note))
        scored.sort(key=lambda pair: -pair[0])
        return [note for _, note in scored[:k]]

    # ------------------------------------------------------------ writes

    @staticmethod
    def write_atomic(path: Path, content: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + f".tmp{os.getpid()}")
        tmp.write_text(content, encoding="utf-8")
        os.replace(tmp, path)

    def write_note(self, rel: str, content: str) -> Path:
        path = self.root / rel
        self.write_atomic(path, content)
        return path

    def append(self, rel: str, content: str) -> Path:
        path = self.root / rel
        existing = path.read_text() if path.exists() else ""
        self.write_atomic(path, existing.rstrip("\n") + "\n\n" + content.lstrip("\n"))
        return path

    # ------------------------------------------------------------ helpers

    def journal_path(self, day: Date) -> Path:
        return self.root / self.cfg.folder("journal") / f"{day.isoformat()}.md"

    def stats_path(self, day: Date, ext: str = "json") -> Path:
        return self.root / self.cfg.folder("stats") / f"{day.isoformat()}.{ext}"

    def dream_files(self, day: Date) -> list[Note]:
        folder = self.cfg.folder("dream")
        prefix = f"{folder}/{day.isoformat()}_"
        return [n for n in self.index() if n.rel.startswith(prefix)]

    def notes_created_on(self, day: Date) -> list[Note]:
        """Creative-output candidates: notes created today, outside managed folders."""
        special = self.special_rel_paths() | {self.cfg.folder("inbox") + "/"}
        out = []
        for note in self.index():
            if note.created_on != day:
                continue
            top = note.rel.split("/")[0]
            if top in {s.rstrip("/") for s in self.special_rel_paths()}:
                continue
            if self.is_ignored(note.rel):
                continue
            if note.words < int(self.cfg.get("creative_output.min_note_length_words", 10)):
                continue
            out.append(note)
        return out

    def token_estimate(self, text: str) -> int:
        return max(1, len(text) // 4)

    # ------------------------------------------------------------ git snapshot safety net

    def git_snapshot(self, message: str) -> bool:
        mode = self.cfg.get("safety.git_snapshots", "if-present")
        if mode == "never" or not (self.root / ".git").exists():
            return False
        import subprocess
        try:
            subprocess.run(["git", "add", "-A"], cwd=self.root, check=True,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            subprocess.run(["git", "commit", "-m", message, "--allow-empty"],
                           cwd=self.root, check=True,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return True
        except Exception:
            return False
