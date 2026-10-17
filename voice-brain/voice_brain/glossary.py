"""Vault-derived glossary -> whisper.cpp ``--prompt`` biasing.

Names, projects and technical terms are exactly what generic STT garbles — and exactly
what the vault already knows. This is the cheapest big STT accuracy win available.
"""

from __future__ import annotations

import re
from pathlib import Path


class Glossary:
    def __init__(self, cfg, vault):
        self.cfg = cfg
        self.vault = vault

    def harvest(self, max_terms: int = 120) -> list[str]:
        """Glossary terms: note titles, wikilink targets, tags, folder names, curated file."""
        terms: dict[str, None] = {}  # ordered set
        curated = self.cfg.path("stt.glossary_file")
        if Path(curated).exists():
            for line in Path(curated).read_text().splitlines():
                term = line.strip()
                if term and not term.startswith("#"):
                    terms[term] = None
        for note in self.vault.index():
            title = note.title
            for word in re.findall(r"[\w][\w\-']{2,}", title):
                if word.isupper() or word[0].isupper():
                    # skip attachments and machine artifacts — they bias whisper badly
                    if re.search(r"[~@]|\.(jpg|jpeg|png|raw|pdf|mp4|mov|webp|gif|wav|md)$", word, re.I):
                        continue
                    terms[word] = None
            for link in note.wikilinks[:3]:
                terms[re.split(r"[|#]", link)[0].strip()] = None
            for tag in note.tags[:3]:
                terms[tag] = None
        return list(terms.keys())[:max_terms]

    def whisper_prompt(self) -> str:
        if not self.cfg.get("stt.glossary_biasing", True):
            return ""
        terms = self.harvest()
        if not terms:
            return ""
        return "Vocabulary: " + ", ".join(terms[:60]) + "."
