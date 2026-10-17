"""Ollama client with the discipline the plan demands:

- every call sets an explicit ``options.num_ctx`` (Ollama's default silently truncates)
- ``format: "json"`` for structured outputs + one repair retry with validation feedback
- ``keep_alive`` keeps the model resident between quick captures
- the LLM narrates, code calculates — prompts receive pre-computed numbers
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Callable

import requests


class LLMError(RuntimeError):
    pass


class ContextTooLarge(LLMError):
    """Raised instead of letting Ollama silently truncate the prompt."""


class JSONValidationError(LLMError):
    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__("; ".join(errors))


_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL)
_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)


def est_tokens(text: str) -> int:
    """Cheap char-based token estimate (~4 chars/token)."""
    return max(1, len(text) // 4)


@dataclass
class Lane:
    model: str
    temperature: float


class OllamaClient:
    def __init__(self, cfg):
        self.cfg = cfg
        self.base_url: str = cfg.get("llm.base_url", "http://localhost:11434").rstrip("/")
        self.keep_alive: str = cfg.get("llm.keep_alive", "30m")
        self.max_num_ctx: int = int(cfg.get("llm.max_num_ctx", 32768))
        self.repair_retries: int = int(cfg.get("llm.repair_retries", 1))
        self._session = requests.Session()

    # ------------------------------------------------------------------ health

    def is_up(self, timeout: float = 2.0) -> bool:
        try:
            self._session.get(f"{self.base_url}/api/version", timeout=timeout)
            return True
        except requests.RequestException:
            return False

    def list_models(self) -> list[str]:
        try:
            resp = self._session.get(f"{self.base_url}/api/tags", timeout=5)
            resp.raise_for_status()
            return [m["name"] for m in resp.json().get("models", [])]
        except (requests.RequestException, ValueError):
            return []

    def model_present(self, model: str) -> bool:
        names = self.list_models()
        return any(n == model or n.split(":")[0] == model for n in names)

    # ------------------------------------------------------------------ core

    def lane(self, which: str) -> Lane:
        if which == "quick":
            return Lane(self.cfg.require("llm.model_quick"),
                       float(self.cfg.get("llm.temperature_quick", 0.4)))
        return Lane(self.cfg.require("llm.model_deep"),
                    float(self.cfg.get("llm.temperature_deep", 0.3)))

    def _num_ctx_for(self, prompt: str, system: str | None) -> int:
        est = est_tokens(prompt) + est_tokens(system or "") + 512  # generation headroom
        want = max(4096, int(est * 2))
        if want > self.max_num_ctx:
            raise ContextTooLarge(
                f"Prompt needs ~{est} tokens (num_ctx {want} > configured max "
                f"{self.max_num_ctx}). Refusing to send: silent truncation is worse than a loud error."
            )
        return want

    def generate(self, prompt: str, *, lane: str = "quick", system: str | None = None,
                 json_mode: bool = False, validator: Callable[[Any], list[str]] | None = None,
                 format_json_schema: dict | None = None) -> Any:
        """Generate. If json_mode, returns parsed JSON (validated); else returns str."""
        ln = self.lane(lane)
        num_ctx = self._num_ctx_for(prompt, system)
        options = {"temperature": ln.temperature, "num_ctx": num_ctx}
        payload: dict[str, Any] = {
            "model": ln.model,
            "prompt": prompt,
            "stream": False,
            "keep_alive": self.keep_alive,
            "options": options,
        }
        if system:
            payload["system"] = system
        if json_mode:
            payload["format"] = format_json_schema or "json"

        text = self._post(payload)
        if not json_mode:
            return text

        return self._parse_json(text, payload, validator)

    # ------------------------------------------------------------------ internals

    def _post(self, payload: dict) -> str:
        try:
            resp = self._session.post(f"{self.base_url}/api/generate", json=payload, timeout=600)
        except requests.RequestException as exc:
            raise LLMError(f"Ollama unreachable at {self.base_url}: {exc}") from exc
        if resp.status_code != 200:
            raise LLMError(f"Ollama error {resp.status_code}: {resp.text[:300]}")
        data = resp.json()
        text = (data.get("response") or "").strip()
        if not text:
            raise LLMError("Ollama returned an empty response")
        return text

    def _parse_json(self, text: str, payload: dict,
                    validator: Callable[[Any], list[str]] | None) -> Any:
        attempts = 1 + self.repair_retries
        last_errors: list[str] = []
        for attempt in range(attempts):
            cleaned = _THINK_RE.sub("", text).strip()
            candidate = cleaned
            fence = _FENCE_RE.search(cleaned)
            if fence:
                candidate = fence.group(1).strip()
            try:
                doc = json.loads(candidate)
            except json.JSONDecodeError as exc:
                last_errors = [f"invalid JSON: {exc}"]
                text = ""
            else:
                if validator is None:
                    return doc
                errs = validator(doc)
                if not errs:
                    return doc
                last_errors = errs
            if attempt < attempts - 1:
                payload = dict(payload)
                payload["prompt"] = (
                    f"{payload['prompt']}\n\n---\nYour previous reply was NOT acceptable:\n"
                    + "\n".join(f"- {e}" for e in last_errors)
                    + "\nReturn the corrected JSON document ONLY. No prose, no markdown fences."
                )
                text = self._post(payload)
        raise JSONValidationError(last_errors or ["JSON parse failed after repair attempt"])
