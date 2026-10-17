"""Relay mode: the slim daemon's job is ears, not brains.

In relay mode (config daemon.mode: relay — the default) every transcript is POSTed to
the Obsidian plugin's capture server. If the plugin is unreachable (Obsidian closed),
the utterance is appended to a pending spool the plugin ingests on next launch —
never lose input. If daemon.mode is "standalone", the legacy full-python pipeline runs.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import requests


class Relay:
    def __init__(self, cfg):
        self.cfg = cfg
        self.url: str = cfg.get("daemon.plugin_url", "http://127.0.0.1:47799").rstrip("/")
        self.token: str = cfg.get("daemon.token", "") or cfg.get("ui.server_token", "")
        self.pending: Path = cfg.state_dir() / "pending.jsonl"

    def is_plugin_up(self, timeout: float = 1.5) -> bool:
        try:
            resp = requests.get(f"{self.url}/health", timeout=timeout)
            return resp.status_code == 200
        except requests.RequestException:
            return False

    def send(self, text: str, source: str = "hotkey",
             confidence: float | None = None) -> str:
        """Returns a human-readable summary. Falls back to the pending spool."""
        payload = {"text": text, "source": source, "ts": time.time(),
                   "confidence": confidence}
        headers = {"Content-Type": "application/json"}
        if self.token:
            headers["X-VB-Token"] = self.token
        try:
            resp = requests.post(f"{self.url}/utterance", json=payload,
                                 headers=headers, timeout=120)
            if resp.status_code == 200:
                data = resp.json()
                return str(data.get("summary", "relayed to Obsidian"))
            raise requests.RequestException(f"plugin returned {resp.status_code}")
        except requests.RequestException as exc:
            self._spool(payload)
            return (f"Obsidian plugin unreachable — saved to pending spool "
                    f"({self.pending.name}, will be ingested on next launch). "
                    f"[{exc}]")

    def _spool(self, payload: dict) -> None:
        self.pending.parent.mkdir(parents=True, exist_ok=True)
        with open(self.pending, "a", encoding="utf-8") as fh:
            fh.write(json.dumps({**payload, "epoch": payload.get("ts", time.time())},
                                ensure_ascii=False) + "\n")
