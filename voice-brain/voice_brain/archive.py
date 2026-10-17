"""Transcript archive: every utterance (timestamp, transcript, route, confidence,
files touched) in a local JSONL. Powers \"what did I say last week about X?\" and the
low-confidence audit trail. Retention configurable."""

from __future__ import annotations

import json
import time
from pathlib import Path


class TranscriptArchive:
    def __init__(self, cfg):
        self.cfg = cfg
        self.file: Path = cfg.state_dir() / "transcripts.jsonl"
        self.retention_days: int = int(cfg.get("archive.retention_days", 365))
        self.file.parent.mkdir(parents=True, exist_ok=True)

    def append(self, text: str, *, route: str, confidence: float | None = None,
               files: list[str] | None = None, source: str = "voice") -> None:
        if not self.cfg.get("archive.transcripts", True):
            return
        entry = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "epoch": time.time(),
            "text": text,
            "route": route,
            "confidence": confidence,
            "files": files or [],
            "source": source,
        }
        with open(self.file, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def entries(self) -> list[dict]:
        if not self.file.exists():
            return []
        out = []
        cutoff = time.time() - self.retention_days * 86400
        for line in self.file.read_text().splitlines():
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            if entry.get("epoch", 0) >= cutoff:
                out.append(entry)
        return out

    def search(self, query: str, k: int = 10) -> list[dict]:
        """Naive TF over archived transcripts (spoken history is small — this is plenty)."""
        terms = [t.lower() for t in query.lower().split() if len(t) > 2]
        scored: list[tuple[float, dict]] = []
        for entry in self.entries():
            text = entry.get("text", "").lower()
            score = sum(text.count(t) for t in terms)
            if score:
                scored.append((score, entry))
        scored.sort(key=lambda p: -p[0])
        return [e for _, e in scored[:k]]

    def streak(self, days: int = 30) -> int:
        """Consecutive-day capture streak (gentle gamification, plan §16.B7)."""
        days_seen = {e["ts"][:10] for e in self.entries()}
        import datetime as _dt
        streak = 0
        day = _dt.date.today()
        while day.isoformat() in days_seen:
            streak += 1
            day -= _dt.timedelta(days=1)
        return streak
