"""Vault-synced settings (Voice Brain Settings/settings.md) — plugin is the
control center, daemon hot-reloads. See voice_brain/settings_sync.py."""

from pathlib import Path

from voice_brain.settings_sync import DEFAULT_CONTENT, VaultSettings, WHITELIST


class _Cfg:
    def __init__(self, root: Path):
        self.data: dict = {}
        self.root = root

    def get(self, dotted, default=None):
        bucket = self.data
        for part in dotted.split("."):
            if not isinstance(bucket, dict) or part not in bucket:
                return default
            bucket = bucket[part]
        return bucket


class _Vault:
    def __init__(self, root: Path):
        self.root = root


def test_settings_sync_applies_whitelist(tmp_path):
    cfg, vault = _Cfg(tmp_path), _Vault(tmp_path)
    f = tmp_path / "Voice Brain Settings"
    f.mkdir(parents=True)
    (f / "settings.md").write_text(
        "# comment\n\nstt_language: ru\nquick_model: other:1b\nbogus_key: x\n")
    vs = VaultSettings(cfg, vault)
    assert vs.check(force=True) == ["stt_language=ru", "quick_model=other:1b"]
    assert cfg.data["stt"]["language"] == "ru"
    assert cfg.data["llm"]["model_quick"] == "other:1b"
    assert "bogus_key" not in str(cfg.data) or "bogus_key" not in cfg.data


def test_settings_sync_ignores_unknown_and_bad_types(tmp_path):
    cfg, vault = _Cfg(tmp_path), _Vault(tmp_path)
    f = tmp_path / "Voice Brain Settings"
    f.mkdir(parents=True)
    (f / "settings.md").write_text(
        "silence_stop_ms: not-a-number\nrandom_thing: 1\n")
    vs = VaultSettings(cfg, vault)
    assert vs.check(force=True) == []
    assert cfg.data == {}


def test_settings_sync_mtime_cache(tmp_path):
    cfg, vault = _Cfg(tmp_path), _Vault(tmp_path)
    f = tmp_path / "Voice Brain Settings"
    f.mkdir(parents=True)
    p = f / "settings.md"
    p.write_text("stt_language: en\n")
    vs = VaultSettings(cfg, vault)
    assert vs.check(force=True) == ["stt_language=en"]
    assert vs.check() == []            # unchanged mtime -> no reapply
    p.write_text("stt_language: pt\n")
    assert vs.check() == ["stt_language=pt"]


def test_default_content_is_whitelisted_only():
    values = {}
    for line in DEFAULT_CONTENT.splitlines():
        line = line.strip()
        if line and not line.startswith("#") and ":" in line:
            key, _, v = line.partition(":")
            values[key.strip()] = v.strip()
    assert values and set(values) <= set(WHITELIST)
