"""\"Brief me\" — morning briefing from yesterday's stats + open TODOs + streaks."""

from __future__ import annotations

import json
from datetime import date as Date, timedelta

from .prompts import brief_me


class Briefer:
    def __init__(self, cfg, vault, llm, archive):
        self.cfg = cfg
        self.vault = vault
        self.llm = llm
        self.archive = archive

    def brief(self, today: Date | None = None) -> str:
        today = today or Date.today()
        stats_file = self.vault.stats_path(today - timedelta(days=1))
        stats_ctx = "(no stats generated yesterday)"
        if stats_file.exists():
            try:
                stats_ctx = stats_file.read_text()[:3000]
            except OSError:
                pass
        todos = sum(n.open_todos for n in self.vault.index())
        streak = self.archive.streak()
        try:
            return self.llm.generate(brief_me(stats_ctx, todos, streak), lane="quick")
        except Exception:
            # Deterministic fallback — a briefing must never fail entirely.
            lines = [f"🌅 Good morning. Open TODOs: {todos}.", f"Capture streak: {streak} days."]
            if stats_file.exists():
                try:
                    doc = json.loads(stats_file.read_text())
                    d = doc.get("derived", {})
                    lines.insert(1, f"Yesterday's readiness: {d.get('readiness_score', '—')}/100.")
                    recs = d.get("recommendations") or []
                    if recs:
                        lines.append(f"💡 {recs[0].get('action', '')}")
                except (json.JSONDecodeError, OSError):
                    pass
            return "\n".join(lines)
