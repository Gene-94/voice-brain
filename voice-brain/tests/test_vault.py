from datetime import date as Date

from voice_brain.vault import Vault, parse_frontmatter, render_frontmatter, slugify


def test_ensure_folders(make_cfg):
    cfg = make_cfg
    vault = Vault(cfg)
    created = vault.ensure_folders()
    assert len(created) == 4
    assert (vault.root / "Dream Journal").exists()
    assert (vault.root / "Dream Journal" / ".voice-brain-generated").exists()
    assert vault.ensure_folders() == []  # idempotent


def test_frontmatter_roundtrip():
    fm = {"title": "Test", "themes": ["flying", "cities"], "vividness": 8}
    text = render_frontmatter(fm) + "# Body\n\ncontent"
    parsed, body = parse_frontmatter(text)
    assert parsed["title"] == "Test"
    assert parsed["themes"] == ["flying", "cities"]
    assert body.startswith("# Body")


def test_index_and_search(make_cfg):
    cfg = make_cfg
    vault = Vault(cfg)
    vault.write_note("Resources/Rust_Async.md",
                     "---\ntitle: Rust Async Patterns\n---\n"
                     "# Rust Async Patterns\nasync tokio runtime notes")
    vault.write_note("Resources/Cooking.md", "# Cooking\nsous vide steak 54 degrees")
    notes = vault.index(rebuild=True)
    assert len(notes) == 2
    hits = vault.search("rust async tokio")
    assert hits and hits[0].title == "Rust Async Patterns"
    assert vault.search("zzz-nomatch") == []


def test_wikilinks_and_todos(make_cfg):
    cfg = make_cfg
    vault = Vault(cfg)
    vault.write_note("A.md", "# A\nSee [[B]] and [[C|alias]] and #rust tag\n- [ ] task")
    note = vault.index(rebuild=True)[0]
    assert set(note.wikilinks) == {"B", "C"}
    assert "rust" in note.tags
    assert note.open_todos == 1


def test_atomic_write(make_cfg):
    cfg = make_cfg
    vault = Vault(cfg)
    vault.write_note("X.md", "first")
    vault.write_note("X.md", "second")
    assert (vault.root / "X.md").read_text() == "second"
    assert not list(vault.root.glob("*.tmp*"))


def test_ignore_file(make_cfg):
    cfg = make_cfg
    vault = Vault(cfg)
    vault.root.mkdir(parents=True)
    (vault.root / ".voice-brain-ignore").write_text("Private/\n")
    vault.write_note("Private/secret.md", "# secret")
    vault.write_note("Public.md", "# public")
    rels = [n.rel for n in vault.index(rebuild=True)]
    assert rels == ["Public.md"]


def test_notes_created_on_excludes_special(make_cfg):
    cfg = make_cfg
    vault = Vault(cfg)
    day = Date(2025, 1, 15)
    vault.write_note("Projects/Spec.md",
                     f"---\ncreated_at: {day.isoformat()}T10:00:00\n---\n" + "# Spec\n" + "word " * 30)
    vault.write_note("Journal/2025-01-15.md", "# Journal\nentry words here today")
    got = vault.notes_created_on(day)
    assert [n.rel for n in got] == ["Projects/Spec.md"]


def test_slugify():
    assert slugify("Flying Over the Neon City!") == "Flying_Over_the_Neon_City"
    assert slugify("") == "untitled"
