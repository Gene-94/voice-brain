"""LLM client discipline tests: num_ctx hard-fail, JSON repair loop."""

import pytest

from voice_brain.llm import (ContextTooLarge, JSONValidationError, LLMError,
                             OllamaClient, est_tokens)


def _client(max_ctx=32768):
    # build a minimal config inline — OllamaClient only touches cfg.get/require
    from voice_brain.config import DEFAULTS, Config, _deep_merge
    data = _deep_merge(DEFAULTS, {"llm": {"max_num_ctx": max_ctx,
                                          "base_url": "http://localhost:1"}})
    return OllamaClient(Config(data))


def test_num_ctx_hard_fail():
    client = _client(max_ctx=8192)
    big = "word " * 40_000  # ~50k tokens
    with pytest.raises(ContextTooLarge):
        client.generate(big)


def test_context_estimated_not_default():
    client = _client()
    small = "hello"
    assert client._num_ctx_for(small, None) >= 4096


def test_json_repair_loop(monkeypatch):
    client = _client()
    bad = '{"a": 1'      # broken JSON
    good = '{"a": 1}'
    calls = {"n": 0}

    def fake_post(payload):
        calls["n"] += 1
        return bad if calls["n"] == 1 else good

    monkeypatch.setattr(client, "_post", fake_post)
    doc = client.generate("x", json_mode=True)
    assert doc == {"a": 1}
    assert calls["n"] == 2  # exactly one repair retry


def test_json_validation_triggers_repair(monkeypatch):
    client = _client()
    wrong = '{"a": 200}'
    right = '{"a": 5}'

    def validator(doc):
        return [] if doc.get("a") == 5 else ["a must be 5"]

    seq = [wrong, right]
    monkeypatch.setattr(client, "_post", lambda p: seq.pop(0))
    assert client.generate("x", json_mode=True, validator=validator) == {"a": 5}


def test_json_validation_fails_loud(monkeypatch):
    client = _client()
    seq = ['{"a": 1}']
    monkeypatch.setattr(client, "_post", lambda p: seq[0])
    with pytest.raises(JSONValidationError):
        client.generate("x", json_mode=True, validator=lambda d: ["always broken"])


def test_llm_unreachable_is_clean_error():
    client = _client()
    with pytest.raises(LLMError):
        client.generate("hello")  # base_url points at a closed port
