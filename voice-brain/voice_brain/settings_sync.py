"""Vault-synced settings — Voice Brain Settings/settings.md.

The Obsidian plugin is the control center: it writes this file; the daemon
hot-reloads it (mtime-cached, checked before every capture) and applies the
whitelisted keys over config.yaml. LiveSync carries the file to every device,
so phone + PC behavior is configured from one place.

Format: one `key: value` per line; `#` comments and blanks ignored. Unknown
keys are ignored (never crash the daemon on a hand-edited file).
"""

from __future__ import annotations

from pathlib import Path

DEFAULT_FILE_REL = "Voice Brain Settings/settings.md"

# synced key -> (config path, type)
WHITELIST: dict[str, tuple[str, type]] = {
    "stt_language": ("stt.language", str),
    "stt_model": ("stt.model", str),
    "quick_model": ("llm.model_quick", str),
    "deep_model": ("llm.model_deep", str),
    "overlay": ("ui.mode", str),          # overlay | notify | none
    "silence_stop_ms": ("audio.silence_stop_ms", int),
    "keep_alive": ("llm.keep_alive", str),
}

DEFAULT_CONTENT = """# Voice Brain — settings (synced to all devices)

# Managed from the Obsidian plugin (Settings -> Voice Brain); the daemon
# hot-reloads this file. Phone and PC both follow it. Edit by hand if you like.

stt_language: auto        # auto | en | pt | ru  (per-capture detection)
stt_model: small          # whisper model (.en models are English-only)
quick_model: gemma4:12b   # fast lane: tags, titles, intent
deep_model: gemma4:12b    # reasoning lane: notes, stats, queries
overlay: overlay          # laptop capture UI: overlay | notify | none
silence_stop_ms: 1200     # laptop mic: ms of silence that ends a capture
keep_alive: 30m           # keep models resident in ollama
"""


class VaultSettings:
    """mtime-cached reader that overlays vault settings onto the live Config."""

    def __init__(self, cfg, vault) -> None:
        self.cfg = cfg
        self.vault = vault
        self._mtime: float | None = None
        self._checked = 0.0

    @property
    def path(self) -> Path:
        rel = self.cfg.get("vault.settings_file", DEFAULT_FILE_REL)
        return self.vault.root / rel

    def ensure_file(self) -> Path | None:
        """Create the settings note on first run. NEVER raises."""
        try:
            path = self.path
            if not path.exists():
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(DEFAULT_CONTENT)
            return path
        except OSError as exc:
            print(f"[settings] cannot create {self.path}: {exc}")
            return None

    def parse(self, text: str) -> dict[str, str]:
        out: dict[str, str] = {}
        for raw in text.splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or ":" not in line:
                continue
            key, _, value = line.partition(":")
            out[key.strip()] = value.partition("#")[0].strip()
        return out

    def _apply(self, values: dict[str, str]) -> list[str]:
        """Overlay whitelisted keys onto cfg.data; returns applied keys."""
        applied: list[str] = []
        for key, value in values.items():
            spec = WHITELIST.get(key)
            if not spec or value == "":
                continue
            dotted, typ = spec
            section, _, leaf = dotted.partition(".")
            try:
                converted = typ(value)
            except (TypeError, ValueError):
                continue
            self.cfg.data.setdefault(section, {})[leaf] = converted
            applied.append(f"{key}={value}")
        return applied

    def check(self, force: bool = False) -> list[str]:
        """Re-read if the file changed; returns the applied keys (empty = no change)."""
        path = self.path
        try:
            mtime = path.stat().st_mtime
        except OSError:
            self.ensure_file()
            return []
        if not force and mtime == self._mtime:
            return []
        try:
            values = self.parse(path.read_text())
        except OSError:
            return []
        self._mtime = mtime
        applied = self._apply(values)
        if applied:
            print(f"[settings] live-reloaded: {', '.join(applied)}")
        return applied
