"""Configuration loading: shipped defaults <- user YAML <- VB_* environment overrides."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

DEFAULTS: dict[str, Any] = {
    "vault": {
        "path": "~/Documents/Obsidian/Omarchy-Yev",
        "managed_folders": {
            "dream": "Dream Journal",
            "journal": "Journal",
            "stats": "Stats",
            "inbox": "Voice Brain Inbox",
        },
        "ignore_file": ".voice-brain-ignore",
        "full_vault_context": "auto",  # auto | always | never
        "full_vault_max_tokens": 120_000,
    },
    "audio": {
        "source": "default",
        "sample_rate": 16000,
        "arm_timeout_s": 15,
        "vad_start_rms": 0.02,
        "vad_start_min_speech_ms": 120,
        "silence_stop_ms": 1200,
        "preroll_s": 0.5,
        "max_recording_s": 90,
        "spool_retention_days": 7,
    },
    "stt": {
        "engine": "whisper-cpp",
        "model": "small",        # multilingual (en-only '.en' models can't hear pt/ru)
        "language": "auto",       # auto | en | pt | ru — per-capture detection
        "beam_size": 5,
        "glossary_biasing": True,
        "glossary_file": "~/.config/voice-brain/glossary.txt",
        "use_silero_trim": True,
    },
    "llm": {
        "base_url": "http://localhost:11434",
        "model_quick": "gemma3:4b",
        "model_deep": "gemma4:latest",  # 7.5B Q4_K_M, 131k ctx (gemma3:9b no longer in registry)
        "keep_alive": "30m",
        "temperature_quick": 0.4,
        "temperature_deep": 0.3,
        "max_num_ctx": 32768,
        "repair_retries": 1,
    },
    "editing": {
        "undo_depth": 10,
    },
    "daemon": {
        "mode": "relay",  # relay (plugin owns the vault) | standalone (full local pipeline)
        "plugin_url": "http://127.0.0.1:47799",
        "token": "",
        "listen_host": "127.0.0.1",  # standalone capture API (phone) — 0.0.0.0 needs a token
        "listen_port": 47799,          # same port as the plugin uses in relay mode (never both)
    },
    "capture": {
        "dictation_mode": True,
        "low_confidence_logprob": -0.8,
    },
    "triggers": {
        "dream": True,
        "journal": True,
        "stats": True,
        "brief": True,
        "general": True,
    },
    "stats": {
        "auto_generate": True,
        "generate_at": "23:59",
        "markdown_summary": True,
        "history_days": 7,
    },
    "creative_output": {
        "enabled": True,
        "assess_quality": True,
        "min_note_length_words": 10,
    },
    "safety": {
        "git_snapshots": "if-present",  # if-present | always | never
        "respect_source_mute": True,
        "battery_guard_percent": 30,
    },
    "ui": {
        "mode": "overlay",  # overlay | notify | none
        "position": "top-right",
    },
    "insights": {
        "min_days_for_correlation": 5,
        "min_n_for_streak": 2,
    },
    "nudges": {"enabled": False, "max_per_day": 2},
    "triage": {"enabled": False, "run_at": "23:30"},
    "archive": {
        "transcripts": True,
        "retention_days": 365,
    },
    "srs": {"enabled": False},
    "paths": {
        "models_dir": "~/.local/share/voice-brain/models",
        "spool_dir": "~/.local/state/voice-brain/spool",
        "state_dir": "~/.local/state/voice-brain",
    },
}


def _deep_merge(base: dict, override: dict) -> dict:
    out = dict(base)
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def _coerce_env(value: str) -> Any:
    lower = value.strip().lower()
    if lower in ("true", "yes"):
        return True
    if lower in ("false", "no"):
        return False
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        pass
    return value


class Config:
    """Dotted-key access over a nested dict, e.g. cfg.get('vault.path')."""

    def __init__(self, data: dict[str, Any]):
        self.data = data

    def get(self, dotted: str, default: Any = None) -> Any:
        node: Any = self.data
        for part in dotted.split("."):
            if not isinstance(node, dict) or part not in node:
                return default
            node = node[part]
        return node

    def require(self, dotted: str) -> Any:
        val = self.get(dotted)
        if val is None:
            raise KeyError(f"Missing required config key: {dotted}")
        return val

    def path(self, dotted: str) -> Path:
        return Path(os.path.expanduser(str(self.require(dotted)))).expanduser()

    @property
    def socket_path(self) -> Path:
        runtime = os.environ.get("XDG_RUNTIME_DIR", f"/tmp/voice-brain-{os.getuid()}")
        return Path(runtime) / "voice-brain.sock"

    def vault_root(self) -> Path:
        return self.path("vault.path").expanduser()

    def state_dir(self) -> Path:
        return self.path("paths.state_dir").expanduser()

    def spool_dir(self) -> Path:
        return self.path("paths.spool_dir").expanduser()

    def models_dir(self) -> Path:
        return self.path("paths.models_dir").expanduser()

    def folder(self, key: str) -> str:
        return self.get(f"vault.managed_folders.{key}", key.title())

    def to_dict(self) -> dict:
        return self.data


def config_file_path() -> Path:
    xdg = os.environ.get("XDG_CONFIG_HOME", "~/.config")
    return Path(os.path.expanduser(xdg)) / "voice-brain" / "config.yaml"


def load_config(path: str | Path | None = None) -> Config:
    """Defaults <- user config file <- VB_* env overrides (VB_VAULT_PATH, VB_LLM_MODEL_DEEP, ...)."""
    data = DEFAULTS
    file = Path(path) if path else config_file_path()
    if file.exists():
        with open(file) as fh:
            user = yaml.safe_load(fh) or {}
        if not isinstance(user, dict):
            raise ValueError(f"{file}: top level must be a mapping")
        data = _deep_merge(data, user)

    # Env overrides: VB_SECTION_KEY=value -> section.key (single level of nesting, underscores ambiguous)
    env: dict[str, Any] = {}
    for key, value in os.environ.items():
        if not key.startswith("VB_"):
            continue
        rest = key[3:].lower()
        for section in DEFAULTS:
            if rest.startswith(section.lower() + "_"):
                sub = rest[len(section) + 1:]
                env[section] = {**(env.get(section) or {}), sub: _coerce_env(value)}
                break
    if env:
        data = _deep_merge(data, env)

    cfg = Config(data)
    for key in ("vault.path", "paths.state_dir", "paths.spool_dir", "paths.models_dir"):
        # fail fast on impossible expansions
        cfg.path(key)
    return cfg


def write_default_config(dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(yaml.safe_dump(DEFAULTS, sort_keys=True))
