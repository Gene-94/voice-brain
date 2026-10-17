"""Vault Q&A: index prefilter -> top-K notes -> deep-lane answer with [[wikilink]] citations.

Also answers \"what did I say about X?\" from the spoken transcript archive.
The LLM narrates; retrieval is deterministic (TF over the index — no vector DB needed).
"""

from __future__ import annotations

from .prompts import query_answer
from .vault import parse_frontmatter

NOTE_BUDGET_TOKENS = 900  # per note in context


class QueryEngine:
    def __init__(self, cfg, vault, llm, archive):
        self.cfg = cfg
        self.vault = vault
        self.llm = llm
        self.archive = archive

    def answer(self, question: str, k: int = 6) -> str:
        q = question.lower()
        if "did i say" in q or "what did i say" in q or "faltei" in q:
            return self._answer_from_archive(question)

        hits = self.vault.search(question, k=k)
        if not hits:
            return ("I couldn't find anything in your vault about that. "
                    "Try different words, or say it in another language.")
        blocks = []
        for note in hits:
            fm, body = parse_frontmatter(note.text)
            truncated = body[: NOTE_BUDGET_TOKENS * 4].strip()
            blocks.append(f"### [{note.title}] (path: {note.rel})\n{truncated}")
        ctx = "\n\n".join(blocks)
        return self.llm.generate(query_answer(question, ctx), lane="deep")

    def _answer_from_archive(self, question: str) -> str:
        hits = self.archive.search(question, k=8)
        if not hits:
            return "Nothing like that in your recent spoken history."
        lines = [f"“{h['text']}” — {h['ts'][:16]} ({h['route']})" for h in hits[:5]]
        return "From what you said recently:\n\n" + "\n".join(lines)
