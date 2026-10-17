"""User-editable trigger patterns — a note in your vault, synced everywhere by LiveSync.

File: <vault>/Settings/voice-brain patterns.md
Format (one rule per line):   <pattern> | <route> [, <folder>]
Routes: dream | journal | note | capture | query | stats | brief
Lines starting with # are comments. First match wins (file order).
The payload sent to the route is what you said MINUS the pattern.

The daemon (Python) and the Obsidian plugin (TypeScript) parse this same file,
so adding a pattern on any device changes routing on all of them.
"""

from __future__ import annotations

import re
import time
from pathlib import Path

DEFAULT_FILE_REL = "Voice Brain Settings/patterns.md"

DEFAULT_CONTENT = """\
# Voice Brain — trigger patterns

Edit on any device — LiveSync keeps this file in sync everywhere.
Each line:  <pattern> | <route> | <optional folder>
The note is written from what you said MINUS the pattern.
Routes: dream, journal, note, capture, query, stats, brief.
First matching line wins.

# Built-ins — English (edit or reorder freely)
I had a dream|dream
I dreamed about|dream
in my dream|dream
last night I dreamt|dream
there was this dream|dream
I have an idea|note|Projects
I want to start a project|note|Projects
log this|journal
log that|journal
journal this|journal
remember this|journal
generate stats|stats
how was my day|stats
analyze my week|stats
brief me|brief
scratch that|scratch

# Português (Portugal)
tive um sonho|dream
sonhei (que|com)|dream
no meu sonho|dream
tive um pesadelo|dream
tenho uma ideia|note|Projects
quero começar um projeto|note|Projects
anota isto|journal
anota isso|journal
regista isto|journal
lembra-te disto|journal
gera as estatísticas|stats
como foi o meu dia|stats
analisa a minha semana|stats
resume-me o dia|brief
esquece isso|scratch

# Русский
мне снился сон|dream
мне приснился сон|dream
во сне|dream
у меня есть идея|note|Projects
у меня идея|note|Projects
есть идея|note|Projects
хочу начать проект|note|Projects
запиши это|journal
запиши|journal
сделай заметку|journal
сгенерируй статистику|stats
сделай статистику|stats
как прошёл мой день|stats
краткий брифинг|brief
брифинг|brief
забудь это|scratch
"""

ROUTES = {"dream", "journal", "note", "capture", "query", "stats", "brief", "scratch"}


class PatternRule:
    __slots__ = ("pattern", "regex", "route", "folder")

    def __init__(self, pattern: str, route: str, folder: str | None):
        self.pattern = pattern
        self.regex = re.compile(pattern.strip(), re.IGNORECASE)
        self.route = route
        self.folder = folder


class Patterns:
    def __init__(self, cfg, vault):
        self.cfg = cfg
        self.vault = vault
        self._cache: list[PatternRule] = []
        self._mtime: float = 0.0
        self._checked: float = 0.0
        self._disabled: bool = False

    @property
    def path(self) -> Path:
        rel = self.cfg.get("vault.patterns_file", DEFAULT_FILE_REL)
        return self.vault.root / rel

    def ensure_file(self) -> Path | None:
        """Create the patterns note on first run. NEVER raises — a broken vault
        layout degrades to built-in triggers instead of crash-looping the daemon."""
        try:
            path = self.path
            if not path.exists():
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(DEFAULT_CONTENT)
            self._disabled = False
            return path
        except OSError as exc:
            self._disabled = True
            self._cache = []
            print(f"[patterns] cannot create {self.path}: {exc} — using built-in triggers")
            return None

    def rules(self, force: bool = False) -> list[PatternRule]:
        """Reload when the file changes (checks mtime at most once per second)."""
        if self._disabled:
            return []
        now = time.time()
        if not force and self._cache and now - self._checked < 1.0:
            return self._cache
        self._checked = now
        path = self.ensure_file()
        try:
            mtime = path.stat().st_mtime
        except OSError:
            return self._cache
        if self._cache and mtime == self._mtime:
            return self._cache
        self._mtime = mtime
        self._cache = self._parse(path.read_text())
        return self._cache

    @staticmethod
    def _parse(text: str) -> list[PatternRule]:
        rules: list[PatternRule] = []
        for raw in text.splitlines():
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            parts = [p.strip() for p in line.split("|")]
            if len(parts) < 2:
                continue
            pattern, route = parts[0], parts[1].lower()
            folder = parts[2] if len(parts) > 2 and parts[2] else None
            if route not in ROUTES:
                continue
            try:
                rules.append(PatternRule(pattern, route, folder))
            except re.error:
                continue  # skip broken regexes, never crash routing
        return rules

    def match(self, text: str) -> tuple[PatternRule, re.Match] | None:
        clean = text.strip()
        for rule in self.rules():
            m = rule.regex.match(clean)
            if m:
                return rule, m
        return None
