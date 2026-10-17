"""End-to-end dispatch tests: Daemon.routing with a fake LLM (no mic, no ollama)."""

from datetime import date as Date

from conftest import FakeLLM
from voice_brain.archive import TranscriptArchive
from voice_brain.config import DEFAULTS, Config, _deep_merge
from voice_brain.patterns import Patterns
from voice_brain.creative_output import CreativeOutput
from voice_brain.daily_journal import JournalRouter
from voice_brain.dream_journal import DreamRouter
from voice_brain.edits import ActionLedger
from voice_brain.notes import NoteWriter
from voice_brain.vault_ops import Organizer
from voice_brain.query import QueryEngine
from voice_brain.stats_generator import StatsGenerator
from voice_brain.ui import NullUI
from voice_brain.vault import Vault


def _app_with(llm, cfg):
    vault = Vault(cfg)
    vault.ensure_folders()
    ledger = ActionLedger(cfg, vault)
    archive = TranscriptArchive(cfg)

    class App:
        pass
    app = App()
    app.cfg = cfg
    app.vault = vault
    app.llm = llm
    app.ledger = ledger
    app.archive = archive
    app.patterns = Patterns(cfg, vault)
    app.dream = DreamRouter(cfg, vault, llm, ledger)
    app.journal = JournalRouter(cfg, vault, llm, ledger)
    app.notes = NoteWriter(cfg, vault, llm, ledger)
    app.query = QueryEngine(cfg, vault, llm, archive)
    app.organizer = Organizer(cfg, vault, llm, ledger)
    app.creative = CreativeOutput(cfg, vault, llm)
    app.stats = StatsGenerator(cfg, vault, llm, ledger)
    return app


def test_dispatch_dream(make_cfg):
    from voice_brain.daemon import Daemon
    llm = FakeLLM({
        "dreams": {"dreams": [{"title": "Ocean City", "summary": "s",
                               "narration": "dream text", "themes": ["water"],
                               "emotional_tone": "calm", "vividness": 7,
                               "lucidity": False}]},
    })
    app = _app_with(llm, make_cfg)
    daemon = Daemon(app, NullUI())
    state, title, body = daemon.dispatch("I had a dream about the ocean")
    assert state == "dream"
    assert "1 dream saved" in title
    assert "Ocean" in body


def test_dispatch_journal_with_llm_down(make_cfg):
    """Full pipeline resilience: LLM outage must never lose the input."""
    from voice_brain.daemon import Daemon
    app = _app_with(FakeLLM(default=None), make_cfg)
    daemon = Daemon(app, NullUI())
    state, title, body = daemon.dispatch("log this: felt great after the gym")
    assert state == "journal"          # journal enrich degrades gracefully
    assert (app.vault.root / "Journal").exists()


def test_raw_transcript_saved_to_inbox(make_cfg):
    """Every utterance leaves a verbatim transcript note in the inbox — written
    before the LLM runs, never in the undo ledger (words survive 'scratch that')."""
    from voice_brain.daemon import Daemon
    app = _app_with(FakeLLM(default=None), make_cfg)
    app.cfg.data["daemon"]["mode"] = "standalone"  # raw transcripts are a standalone-profile feature
    daemon = Daemon(app, NullUI())
    before = set((app.vault.root / "Voice Brain Inbox").glob("*"))
    daemon._process_text("tenho uma ideia maravilhosa", "text")
    after = set((app.vault.root / "Voice Brain Inbox").glob("*transcript-*.md"))
    new = after - before
    assert len(new) == 1
    text = new.pop().read_text()
    assert "tenho uma ideia maravilhosa" in text


def test_dispatch_general_capture_polished(make_cfg):
    """Unknown utterances now get POLISHED by the LLM (bullets, structure) into the inbox."""
    from voice_brain.daemon import Daemon
    llm = FakeLLM({
        "kind": {"kind": "capture", "reason": "unclear"},
        "You clean up a RAW voice transcript": {"title": "Random Thoughts",
                                                 "content": "- polished bullet",
                                                 "tags": ["capture"]},
    })
    app = _app_with(llm, make_cfg)
    daemon = Daemon(app, NullUI())
    state, title, body = daemon.dispatch("something something unintelligible")
    assert state == "note"
    assert "Voice Brain Inbox" in body
    note = (app.vault.root / body).read_text()
    assert "Random Thoughts" in note
    assert "Raw transcript" not in note      # raw now lives as its own inbox note


def test_dispatch_polish_down_falls_back_to_verbatim(make_cfg):
    """LLM down: loud error + the words still land verbatim (never lose input)."""
    from voice_brain.daemon import Daemon
    app = _app_with(FakeLLM({"kind": {"kind": "capture", "reason": "unclear"}}),
                    make_cfg)
    daemon = Daemon(app, NullUI())
    state, title, body = daemon.dispatch("words that must survive")
    assert state == "error"
    assert "Words saved" in body
    assert "words that must survive" in (app.vault.root / body.splitlines()[1].split("saved to ")[-1]).read_text()


def test_dispatch_scratch(make_cfg):
    from voice_brain.daemon import Daemon
    app = _app_with(FakeLLM(default=None), make_cfg)
    daemon = Daemon(app, NullUI())
    # create something to undo first
    rel = app.notes.capture("to be undone")
    state, title, body = daemon.dispatch("scratch that")
    assert state == "success"
    assert not (app.vault.root / rel).exists()
    # undo again -> loud error, no crash
    state, title, body = daemon.dispatch("scratch that")
    assert state == "error"


def test_query_citations(make_cfg):
    from voice_brain.daemon import Daemon
    app = _app_with(FakeLLM({
        "kind": {"kind": "query", "reason": "question"},
        "Question:": "You use [[Networking - Packets]] for that.",
    }), make_cfg)
    app.vault.write_note("Resources/Networking - Packets.md",
                         "# Networking - Packets\npackets switching routing")
    daemon = Daemon(app, NullUI())
    state, title, body = daemon.dispatch("what do I know about packets?")
    assert state == "query"
    assert "[[Networking - Packets]]" in body


def test_stats_generation_end_to_end(make_cfg):
    llm = FakeLLM(default=None)
    responses = {
        "Quantified Self analysis engine": _valid_stats_doc(),
    }
    llm.responses = responses
    app = _app_with(llm, make_cfg)
    # give it inputs: journal entry
    app.journal._enrich = lambda text: ("Log", [])
    import datetime as dt
    day = dt.date.today()
    path = app.vault.journal_path(day)
    app.vault.write_atomic(path, "---\ndate: '%s'\n---\n\n# Journal\n\nworked out, slept great\n" % day)
    out = app.stats.generate(day)
    import json
    doc = json.loads(out.read_text())
    assert doc["date"] == day.isoformat()          # code sets authority fields
    assert doc["schema_version"] == "1.0.0"
    assert isinstance(doc["derived"]["readiness_score"], int)


def _valid_stats_doc():
    cats = ("sleep", "mood", "energy", "physical", "nutrition", "cognitive",
            "creative_output", "social", "environment", "habits", "time_use")
    doc = {c: {"notes": "fine", "source": "Journal"} for c in cats}
    doc.update({
        "date": "2025-01-15",
        "generated_at": "2025-01-15T23:59:00",
        "derived": {"readiness_score": 74, "wellbeing_index": 7.1,
                    "recommendations": [{"priority": 1, "action": "walk",
                                          "rationale": "because", "confidence": 0.8}]},
        "insights": {"narrative": "Solid day.", "correlations": []},
        "creative_output": {"notes_created_count": 0, "notes": "none", "source": "scan"},
    })
    return doc
