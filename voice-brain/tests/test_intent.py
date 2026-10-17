from voice_brain.intent import Kind, classify


def test_dream_trigger_primary():
    assert classify("I had a dream where I was flying").kind is Kind.DREAM

def test_dream_variants():
    for text in ("I dreamed about the ocean last night",
                 "In my dream my teeth fell out",
                 "Last night I dreamt I was late for an exam",
                 "There was this dream where a fox talked to me"):
        assert classify(text).kind is Kind.DREAM, text

def test_priority_dream_beats_journal_in_body():
    # "log this: I had a dream..." — dream prefix at start wins? Per spec the dream
    # prefix takes priority when both appear; our regex is start-anchored, so a
    # leading "log this" routes to journal. Spec rule: dream wins when BOTH are first
    # phrases — i.e. "I had a dream" leading routes to dream even if "log this" follows.
    assert classify("I had a dream, log this please").kind is Kind.DREAM

def test_journal_triggers():
    for text in ("log this: great workout", "log that", "journal this: idea",
                 "remember this for later", "anota isso pra mim"):
        assert classify(text).kind is Kind.JOURNAL, text

def test_stats_triggers():
    assert classify("generate stats").kind is Kind.STATS
    assert classify("how was my day?").kind is Kind.STATS
    assert classify("analyze my week").kind is Kind.STATS

def test_brief():
    assert classify("brief me").kind is Kind.BRIEF

def test_scratch():
    assert classify("scratch that").kind is Kind.SCRATCH
    assert classify("undo that please").kind is Kind.SCRATCH

def test_general_fallthrough():
    assert classify("what do I know about async rust").kind is Kind.GENERAL
    assert classify("").kind is Kind.GENERAL

def test_payload_strips_trigger():
    intent = classify("log this: went for a run at 7am")
    assert intent.payload == "went for a run at 7am"

def test_triggers_can_be_disabled():
    from voice_brain.config import DEFAULTS, Config, _deep_merge
    data = _deep_merge(DEFAULTS, {"triggers": {"dream": False}})
    assert classify("I had a dream about flying", Config(data)).kind is Kind.GENERAL
