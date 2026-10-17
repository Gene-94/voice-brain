"""Shared fixtures: temp-vault config + fake LLM."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from voice_brain.config import DEFAULTS, Config, _deep_merge  # noqa: E402


@pytest.fixture
def make_cfg(tmp_path: Path, **overrides) -> Config:
    data = _deep_merge(DEFAULTS, {
        "vault": {"path": str(tmp_path / "vault")},
        "paths": {
            "state_dir": str(tmp_path / "state"),
            "spool_dir": str(tmp_path / "state" / "spool"),
            "models_dir": str(tmp_path / "models"),
        },
    })
    if overrides:
        data = _deep_merge(data, overrides)
    return Config(data)


class FakeLLM:
    """Stand-in for OllamaClient. `responses` maps a prompt substring -> parsed-JSON doc.
    Unmatched prompts fall through to `default` (if set) else raise."""

    def __init__(self, responses: dict[str, object] | None = None, default=None):
        self.responses = responses or {}
        self.default = default
        self.calls: list[str] = []

    def lane(self, which):
        from voice_brain.llm import Lane
        return Lane(f"fake:{which}", 0.1)

    def generate(self, prompt, *, lane="quick", system=None, json_mode=False,
                 validator=None, **_):
        self.calls.append(prompt)
        if prompt in self.responses:
            doc = self.responses[prompt]
        else:
            for key, doc in self.responses.items():
                if key in prompt:
                    break
            else:
                if self.default is not None:
                    doc = self.default
                else:
                    from voice_brain.llm import LLMError
                    raise LLMError(f"no fake response for: {prompt[:60]}…")
        if validator:
            errs = validator(doc)
            if errs:
                from voice_brain.llm import LLMError
                raise LLMError(f"fake doc failed validation: {errs}")
        return doc
