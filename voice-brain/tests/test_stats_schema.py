from voice_brain.stats_schema import validate_stats


def _doc(**over):
    doc = {
        "date": "2025-01-15",
        "generated_at": "2025-01-15T23:59:00",
        "derived": {"readiness_score": 74, "wellbeing_index": 7.1,
                    "recommendations": [{"priority": 1, "action": "test"}]},
        "insights": {"narrative": "A good day overall."},
    }
    for cat in ("sleep", "mood", "energy", "physical", "nutrition", "cognitive",
                "creative_output", "social", "environment", "habits", "time_use"):
        doc[cat] = {"notes": "ok", "source": "Journal/2025-01-15.md"}
    doc.update(over)
    return doc


def test_valid_doc_passes():
    assert validate_stats(_doc()) == []

def test_missing_category_flagged():
    doc = _doc()
    del doc["sleep"]
    errs = validate_stats(doc)
    assert any("sleep" in e for e in errs)

def test_missing_notes_flagged():
    doc = _doc()
    doc["sleep"] = {"source": "x"}
    assert any("sleep.notes" in e for e in validate_stats(doc))

def test_range_checks():
    doc = _doc()
    doc["derived"]["readiness_score"] = 150
    doc["mood"]["average_score"] = 12
    errs = validate_stats(doc)
    assert any("readiness_score" in e for e in errs)
    assert any("average_score" in e for e in errs)

def test_empty_recommendations_rejected():
    doc = _doc()
    doc["derived"]["recommendations"] = []
    assert any("recommendations" in e for e in validate_stats(doc))

def test_non_object():
    assert validate_stats([1, 2]) == ["top-level must be a JSON object"]
