"""Creative Output Tracking: what you PRODUCED today (vs consumed/logged).

Deterministic parts (file discovery, word counts, link density -> connectivity) are computed
in code; the LLM only assesses quality dimensions (novelty, depth, clarity, actionability)
and classifies domain/format. The LLM can't count links — so it doesn't.
"""

from __future__ import annotations

import json
from datetime import date as Date

from .prompts import PROMPT_VERSIONS, creative_assess


def _validate(doc: object) -> list[str]:
    if not isinstance(doc, dict) or "assessments" not in doc:
        return ["must contain 'assessments' list"]
    if not isinstance(doc["assessments"], list):
        return ["'assessments' must be a list"]
    return []


class CreativeOutput:
    def __init__(self, cfg, vault, llm):
        self.cfg = cfg
        self.vault = vault
        self.llm = llm

    def collect(self, day: Date) -> dict:
        """Full creative_output block for the stats JSON. Safe on zero notes."""
        notes = self.vault.notes_created_on(day) \
            if self.cfg.get("creative_output.enabled", True) else []
        notes = [n for n in notes if n.words >=
                 int(self.cfg.get("creative_output.min_note_length_words", 10))]

        block: dict = {
            "notes_created_count": len(notes),
            "notes_created_today": [n.rel for n in notes],
            "total_words_produced": sum(n.words for n in notes),
            "domains": sorted({n.frontmatter.get("domain", "unknown") for n in notes})
                       if notes else [],
            "formats": sorted({n.frontmatter.get("format", "note") for n in notes})
                       if notes else [],
            "creativity_score_unit": "0-100",
            "source": "Vault filesystem scan + Gemma assessment",
            "prompt_version": PROMPT_VERSIONS["creative_assess"],
        }
        if not notes:
            block.update({k: 0 for k in ("novelty_average", "depth_average",
                                         "connectivity_average", "clarity_average",
                                         "actionability_average", "creativity_score")})
            block["notes"] = "No creative notes produced today."
            return block

        # deterministic connectivity: wikilink density per note (0-10)
        connectivity = [min(10, len(n.wikilinks) * 2 + 1) for n in notes]

        if self.cfg.get("creative_output.assess_quality", True):
            blocks = []
            for n in notes:
                blocks.append(f"[{n.rel}]\n{n.body[:600].strip()}")
            doc = self.llm.generate(creative_assess("\n\n".join(blocks)), lane="deep",
                                    json_mode=True, validator=_validate)
            by_rel = {a.get("rel"): a for a in doc.get("assessments", [])
                      if isinstance(a, dict)}
            dims = {"novelty": [], "depth": [], "clarity": [], "actionability": []}
            domains, formats = [], []
            for n in notes:
                a = by_rel.get(n.rel) or {}
                for dim in dims:
                    val = a.get(dim)
                    if isinstance(val, (int, float)) and 0 <= val <= 10:
                        dims[dim].append(float(val))
                if a.get("domain"):
                    domains.append(str(a["domain"]))
                if a.get("format"):
                    formats.append(str(a["format"]))
            avg = {dim: round(sum(vals) / len(vals), 1) if vals else 0
                   for dim, vals in dims.items()}
            conn_avg = round(sum(connectivity) / len(connectivity), 1)
            block["domains"] = sorted(set(domains)) or block["domains"]
            block["formats"] = sorted(set(formats)) or block["formats"]
        else:
            avg = {dim: 0 for dim in ("novelty", "depth", "clarity", "actionability")}
            conn_avg = round(sum(connectivity) / len(connectivity), 1)

        for dim in avg:
            block[f"{dim}_average"] = avg[dim]
            block[f"{dim}_average_scale"] = "0-10"
        block["connectivity_average"] = conn_avg
        block["connectivity_average_scale"] = "0-10"
        quality = (avg["novelty"] + avg["depth"] + conn_avg + avg["clarity"]
                   + avg["actionability"]) / 5 * 10  # 0-100
        block["creativity_score"] = round(quality)
        peak = min(notes, key=lambda n: -n.mtime, default=None)
        if peak:
            block["peak_creative_time"] = peak.mtime
        block["notes"] = (f"{len(notes)} notes, {block['total_words_produced']} words. "
                          f"Connectivity {conn_avg}/10 (deterministic link count).")
        return block
