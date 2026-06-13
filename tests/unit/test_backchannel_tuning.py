from __future__ import annotations

from app.backchannel.tuning import (
    ScoredExample,
    evaluate_point,
    frange,
    predict,
    sweep,
)


def _ex(text: str, gold: str | None, ranked: list[tuple[str, float]]) -> ScoredExample:
    return ScoredExample(text=text, gold_intent=gold, ranked=tuple(ranked))


def test_predict_replicates_threshold_and_margin() -> None:
    ex = _ex("x", "request", [("request", 0.90), ("question", 0.70)])
    assert predict(ex, threshold=0.86, margin=0.08) == "request"
    # 低于 threshold → 弃权
    assert predict(ex, threshold=0.95, margin=0.08) is None
    # margin 不足 → 弃权
    assert predict(ex, threshold=0.86, margin=0.30) is None


def test_predict_empty_ranked_abstains() -> None:
    assert predict(_ex("x", None, []), 0.5, 0.0) is None


def test_evaluate_point_counts_correct_wrong_abstain() -> None:
    examples = [
        _ex("a", "request", [("request", 0.95), ("question", 0.5)]),   # correct
        _ex("b", "question", [("request", 0.95), ("question", 0.5)]),  # wrong
        _ex("c", "support", [("support", 0.80), ("sad", 0.79)]),       # below thr → abstain
        _ex("d", None, [("request", 0.70), ("question", 0.4)]),        # gold None, abstains → correct
    ]
    point = evaluate_point(examples, threshold=0.86, margin=0.08)
    assert point.correct == 1
    assert point.wrong == 1
    assert point.abstained == 2
    # correct(1) + correct_abstain(d) = 2 / 4
    assert point.accuracy == 0.5


def test_sweep_ranks_best_first_and_is_exhaustive() -> None:
    examples = [
        _ex("a", "request", [("request", 0.90), ("question", 0.60)]),
        _ex("b", "support", [("support", 0.88), ("sad", 0.62)]),
    ]
    thresholds = frange(0.80, 0.95, 0.01)
    margins = frange(0.00, 0.10, 0.01)
    points = sweep(examples, thresholds, margins)
    assert len(points) == len(thresholds) * len(margins)
    best = points[0]
    # 两条都能在 thr<=0.88, margin<=0.26 直采且正确
    assert best.accuracy == 1.0
    assert best.wrong == 0


def test_frange_inclusive_and_safe() -> None:
    assert frange(0.0, 0.2, 0.1) == [0.0, 0.1, 0.2]
    assert frange(0.5, 0.5, 0.0) == [0.5]
