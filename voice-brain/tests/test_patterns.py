"""User-editable pattern routing: vault file -> routes on all devices."""

from voice_brain.intent import Kind, classify
from voice_brain.patterns import Patterns
from voice_brain.vault import Vault


def _make(make_cfg):
    cfg = make_cfg
    vault = Vault(cfg)
    vault.root.mkdir(parents=True, exist_ok=True)
    return Patterns(cfg, vault)


def test_default_file_created_and_parsed(make_cfg):
    p = _make(make_cfg)
    path = p.ensure_file()
    assert path and path.exists()
    assert path.name == "patterns.md"
    assert "Voice Brain Settings" in path.parent.name
    rules = p.rules(force=True)
    routes = {r.route for r in rules}
    assert {"dream", "journal", "note", "stats", "brief"} <= routes


def test_idea_pattern_routes_to_projects(make_cfg):
    p = _make(make_cfg)
    p.rules(force=True)
    intent = classify("I have an idea: a sink that also dries the dishes",
                      patterns=p)
    assert intent.kind is Kind.NOTE
    assert intent.folder == "Projects"
    assert intent.payload == "a sink that also dries the dishes"  # pattern stripped


def test_dream_pattern_still_works_via_file(make_cfg):
    p = _make(make_cfg)
    p.rules(force=True)
    intent = classify("I had a dream where the sea was glass", patterns=p)
    assert intent.kind is Kind.DREAM
    assert "sea was glass" in intent.payload


def test_first_match_wins_and_custom_override(make_cfg):
    p = _make(make_cfg)
    path = p.ensure_file()
    path.write_text(
        "I have an idea|note|Projects\n"
        "I have an idea for a game|note|Gaming\n")
    intent = classify("I have an idea for a game about tiles",
                      patterns=p)
    assert intent.folder == "Projects"  # file order wins


def test_broken_regex_and_unknown_route_skipped(make_cfg):
    p = _make(make_cfg)
    path = p.ensure_file()
    path.write_text("I have (broken|note\nthing|unknownroute\nlog it|journal\n")
    rules = p.rules(force=True)
    assert [r.pattern for r in rules] == ["log it"]
    intent = classify("I have (broken something", patterns=p)
    assert intent.kind is Kind.GENERAL  # bad rules never crash routing


def test_reload_on_file_change(make_cfg):
    p = _make(make_cfg)
    p.rules(force=True)
    path = p.ensure_file()
    path.write_text("eta volar|note|Random\n")
    intent = classify("eta volar de noite", patterns=p)
    assert intent.kind is Kind.GENERAL  # not yet visible (mtime cache)
    import time
    path.write_text("eta volar|note|Random\n")  # rewrite -> new mtime
    time.sleep(0.02)
    p._checked = 0.0  # force the 1s throttle open
    intent = classify("eta volar de noite", patterns=p)
    assert intent.kind is Kind.NOTE and intent.folder == "Random"


def test_multilingual_patterns_pt_ru(make_cfg):
    """PT-PT and Russian routes work from the same vault patterns file."""
    p = _make(make_cfg)
    p.rules(force=True)

    # Português (Portugal)
    intent = classify("Tive um sonho onde voava sobre o Porto", patterns=p)
    assert intent.kind is Kind.DREAM
    assert "voava sobre o Porto" in intent.payload
    intent = classify("Tenho uma ideia: uma aplicação para regar plantas", patterns=p)
    assert intent.kind is Kind.NOTE and intent.folder == "Projects"
    assert intent.payload.startswith("uma aplicação")
    intent = classify("Anota isto: hoje foi um bom dia", patterns=p)
    assert intent.kind is Kind.JOURNAL

    # Русский
    intent = classify("Мне снился сон про море", patterns=p)
    assert intent.kind is Kind.DREAM
    assert "море" in intent.payload
    intent = classify("У меня есть идея: сделать умный дом", patterns=p)
    assert intent.kind is Kind.NOTE and intent.folder == "Projects"
    intent = classify("Запиши это: сегодня был хороший день", patterns=p)
    assert intent.kind is Kind.JOURNAL
    intent = classify("Забудь это", patterns=p)
    assert intent.kind is Kind.SCRATCH


def test_patterns_used_in_dispatch(make_cfg):
    """The daemon routes through the vault pattern file, end to end (raw
    transcript saved separately in the inbox by _process_text — not by dispatch)."""
    from conftest import FakeLLM
    from voice_brain.archive import TranscriptArchive
    from voice_brain.daemon import Daemon
    from voice_brain.edits import ActionLedger
    from voice_brain.notes import NoteWriter
    from voice_brain.ui import NullUI
    import voice_brain.app as app_mod

    cfg = make_cfg
    vault = Vault(cfg)
    vault.ensure_folders()
    vault.root.mkdir(parents=True, exist_ok=True)
    ledger = ActionLedger(cfg, vault)
    archive = TranscriptArchive(cfg)
    llm = FakeLLM({"title": {"title": "Flying Dish Dryer", "content": "- idea notes",
                             "tags": ["ideas"]}})

    class App:
        pass
    app = App()
    app.cfg = cfg
    app.vault = vault
    app.llm = llm
    app.ledger = ledger
    app.archive = archive
    app.patterns = Patterns(cfg, vault)
    app.notes = NoteWriter(cfg, vault, llm, ledger)

    daemon = Daemon(app, NullUI())
    state, title, body = daemon.dispatch(
        "I have an idea: a sink that also dries the dishes")
    assert state == "note"
    assert body.startswith("Projects/")
    text = (vault.root / body).read_text()
    assert "Flying Dish Dryer" in text
    assert "Raw transcript" not in text    # raw now lives as its own inbox note
