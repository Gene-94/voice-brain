"""Router tests with a fake LLM — the dream split, journal append, capture fallback,
undo ledger, and the never-lose-input guarantee."""

from datetime import datetime

from conftest import FakeLLM, make_cfg  # noqa: F401 (fixture import)
from voice_brain.archive import TranscriptArchive
from voice_brain.daily_journal import JournalRouter
from voice_brain.dream_journal import DreamRouter
from voice_brain.edits import ActionLedger
from voice_brain.notes import NoteWriter
from voice_brain.vault import Vault, parse_frontmatter

NOW = datetime(2025, 1, 15, 8, 15)

DREAM_RESPONSE = {
    "dreams": [
        {"title": "Flying Over the Neon City", "summary": "Flying between skyscrapers.",
         "narration": "I was flying over a neon-lit city", "themes": ["flying", "cities"],
         "emotional_tone": "exhilarated", "vividness": 8, "lucidity": False},
        {"title": "High School Cat Classmates", "summary": "Everyone was a cat.",
         "narration": "everyone at school was a cat", "themes": ["school", "animals"],
         "emotional_tone": "absurd", "vividness": 6, "lucidity": False},
    ]
}

ENRICH_RESPONSE = {"heading": "Morning Energy", "tags": ["mood=8", "exercise=deadlifts"]}
NOTE_RESPONSE = {"title": "Rust Error Handling", "content": "# Rust\n\nContent here.",
                 "tags": ["rust", "programming"]}


def _dream_fixture(cfg):
    vault = Vault(cfg)
    vault.ensure_folders()
    ledger = ActionLedger(cfg, vault)
    llm = FakeLLM({"dreams": DREAM_RESPONSE})  # matches any prompt containing 'dreams'
    router = DreamRouter(cfg, vault, llm, ledger)
    return cfg, vault, ledger, router


def test_dream_split_creates_one_file_per_dream(make_cfg):
    cfg, vault, ledger, router = _dream_fixture(make_cfg)
    files = router.handle("I had a dream where I was flying over a neon city... "
                          "and also everyone at school was a cat", now=NOW)
    assert len(files) == 2
    assert files[0] == "Dream Journal/2025-01-15_Flying_Over_the_Neon_City.md"
    fm, body = parse_frontmatter((vault.root / files[0]).read_text())
    assert fm["title"] == "Flying Over the Neon City"
    assert fm["vividness"] == 8
    assert fm["themes"] == ["flying", "cities"]
    assert "flying over a neon-lit city" in body


def test_dream_ledger_undo(make_cfg):
    cfg, vault, ledger, router = _dream_fixture(make_cfg)
    files = router.handle("I had a dream about flying", now=NOW)
    assert len(files) == 2
    msg = ledger.undo_last()
    assert "Undid" in msg
    assert not (vault.root / files[0]).exists()
    assert ledger.last() is None


def test_dream_ledger_refuses_undo_after_user_edit(make_cfg):
    cfg, vault, ledger, router = _dream_fixture(make_cfg)
    files = router.handle("dream", now=NOW)
    path = vault.root / files[0]
    path.write_text(path.read_text() + "\nuser edit")  # user touches the file
    msg = ledger.undo_last()
    assert "edited since" in msg
    assert path.exists()


def test_journal_append_and_count(make_cfg):
    cfg = make_cfg
    vault = Vault(cfg)
    vault.ensure_folders()
    ledger = ActionLedger(cfg, vault)
    router = JournalRouter(cfg, vault, FakeLLM({"heading": ENRICH_RESPONSE}), ledger)
    path = router.handle("just finished a great workout, feel energized", now=NOW)
    assert path.name == "2025-01-15.md"
    text = path.read_text()
    assert "## 08:15 — Morning Energy" in text
    assert "<!--vb: mood=8 exercise=deadlifts -->" in text
    router.handle("team lunch was fun", now=datetime(2025, 1, 15, 12, 30))
    fm, body = parse_frontmatter(path.read_text())
    assert fm["entry_count"] == 2
    assert "12:30" in body


def test_journal_survives_llm_outage(make_cfg):
    """Enrichment is optional — the write must never be blocked (resilience)."""
    cfg = make_cfg
    vault = Vault(cfg)
    ledger = ActionLedger(cfg, vault)
    router = JournalRouter(cfg, vault, FakeLLM(default=None), ledger)
    path = router.handle("slept badly, woke twice", now=NOW)
    text = path.read_text()
    assert "slept badly" in text


def test_note_create(make_cfg):
    cfg = make_cfg
    vault = Vault(cfg)
    vault.ensure_folders()
    ledger = ActionLedger(cfg, vault)
    writer = NoteWriter(cfg, vault, FakeLLM({"title": NOTE_RESPONSE}), ledger)
    rel = writer.create("create a new note on rust error handling", now=NOW)
    assert rel.startswith("Voice Brain Inbox/2025-01-15_Rust_Error")
    fm, _ = parse_frontmatter((vault.root / rel).read_text())
    assert fm["created_by"] == "voice-brain"


def test_capture_never_calls_llm(make_cfg):
    cfg = make_cfg
    vault = Vault(cfg)
    vault.ensure_folders()
    ledger = ActionLedger(cfg, vault)
    llm = FakeLLM(default=None)
    writer = NoteWriter(cfg, vault, llm, ledger)
    rel = writer.capture("random garbled words", now=NOW)
    assert "capture" in rel
    assert llm.calls == []  # safety net never depends on the LLM


def test_archive_search_and_streak(make_cfg):
    cfg = make_cfg
    arch = TranscriptArchive(cfg)
    arch.append("I talked about rust today", route="journal")
    hits = arch.search("rust")
    assert hits and "rust" in hits[0]["text"]
    assert arch.streak() >= 1
