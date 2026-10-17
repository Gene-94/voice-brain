from datetime import date as Date

from voice_brain.insights import (capture_streak, cc_ratio, compute_correlations,
                                  compute_trend, pearson, zscore)


def test_pearson_perfect():
    assert pearson([1, 2, 3], [2, 4, 6]) == 1.0
    assert pearson([1, 2, 3], [6, 4, 2]) == -1.0

def test_pearson_insufficient():
    assert pearson([1, 2], [2, 4]) is None

def test_zscore_outlier():
    z = zscore(10.0, [1.0, 1.1, 0.9, 1.0, 1.2])
    assert z > 2

def test_cc_ratio():
    r = cc_ratio(300, 100)
    assert r["cc_ratio"] == 3.0
    assert r["cc_ratio_note"]
    assert cc_ratio(100, 0)["cc_ratio"] is None

def test_correlations_need_evidence():
    hist = [{"derived": {"wellbeing_index": 6},
             "sleep": {"quality_score": 70},
             "creative_output": {"creativity_score": 60}} for _ in range(3)]
    # 3 days < min_days=5 -> no correlations reported
    assert compute_correlations(hist, min_days=5) == []
    hist5 = [{"derived": {"wellbeing_index": 6 + i},
              "sleep": {"quality_score": 60 + i * 10},
              "creative_output": {"creativity_score": 50}} for i in range(6)]
    corrs = compute_correlations(hist5, min_days=5)
    assert corrs and corrs[0]["n_day_support"] == 6
    assert corrs[0]["relationship"] == "positive"

def test_trend_delta():
    hist = [{"derived": {"readiness_score": 70}}, {"derived": {"readiness_score": 72}}]
    today = {"derived": {"readiness_score": 80}}
    trend = compute_trend(today, hist)
    assert "up" in trend["trending"]
    assert compute_trend(None, [])["trending"] == "unknown"

def test_capture_streak():
    today = Date(2025, 1, 15)
    days = {Date(2025, 1, 15), Date(2025, 1, 14), Date(2025, 1, 13)}
    assert capture_streak([], days, today) == 3
    assert capture_streak([], {Date(2025, 1, 10)}, today) == 0
