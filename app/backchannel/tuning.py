from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence

# 阈值调参:目标(准确率)是 threshold/margin 的分段常数函数,不可导。
# 2 维标量 + 编码可缓存 → 对缓存分数做穷举网格搜索即精确全局最优,
# 远优于梯度法/进化策略(后者只在高维 + 平滑代理目标下才划算)。


@dataclass(frozen=True)
class ScoredExample:
    """一条评测样本及其(预先编码好的)各意图相似度。

    ranked 按相似度降序;gold_intent 为人工标注的正确意图,
    None 表示该样本不应触发模型直采(期望落 fallback / 不接话)。
    """

    text: str
    gold_intent: str | None
    ranked: tuple[tuple[str, float], ...]

    def top(self) -> tuple[str, float] | None:
        return self.ranked[0] if self.ranked else None

    def second_score(self) -> float:
        return self.ranked[1][1] if len(self.ranked) > 1 else -1.0


def predict(example: ScoredExample, threshold: float, margin: float) -> str | None:
    """复刻 EmbeddingIntentClassifier 的判定:过 threshold 且 margin 足够才直采。"""
    head = example.top()
    if head is None:
        return None
    best_intent, best_score = head
    if best_score < threshold:
        return None
    if best_score - example.second_score() < margin:
        return None
    return best_intent


@dataclass(frozen=True)
class GridPoint:
    threshold: float
    margin: float
    accuracy: float
    direct: int          # 模型给出意图的样本数
    correct: int         # 直采且正确
    wrong: int           # 直采但错(最该压低的代价)
    abstained: int       # 未直采(落 fallback / 不接话)


def evaluate_point(
    examples: Sequence[ScoredExample],
    threshold: float,
    margin: float,
) -> GridPoint:
    correct = wrong = abstained = 0
    for example in examples:
        predicted = predict(example, threshold, margin)
        if predicted is None:
            abstained += 1
            continue
        if predicted == example.gold_intent:
            correct += 1
        else:
            wrong += 1
    total = len(examples) or 1
    # 准确率把"正确弃权(gold 本就是 None)"也算对:保守不接话不算错。
    correct_abstain = sum(
        1
        for example in examples
        if example.gold_intent is None and predict(example, threshold, margin) is None
    )
    accuracy = (correct + correct_abstain) / total
    return GridPoint(
        threshold=round(threshold, 4),
        margin=round(margin, 4),
        accuracy=accuracy,
        direct=correct + wrong,
        correct=correct,
        wrong=wrong,
        abstained=abstained,
    )


def sweep(
    examples: Sequence[ScoredExample],
    thresholds: Iterable[float],
    margins: Iterable[float],
) -> list[GridPoint]:
    """全网格评估,按(准确率高、错采少、弃权少)排序。"""
    points = [
        evaluate_point(examples, threshold, margin)
        for threshold in thresholds
        for margin in margins
    ]
    points.sort(key=lambda p: (p.accuracy, -p.wrong, -p.abstained), reverse=True)
    return points


def frange(start: float, stop: float, step: float) -> list[float]:
    if step <= 0:
        return [round(start, 4)]
    values: list[float] = []
    current = start
    while current <= stop + 1e-9:
        values.append(round(current, 4))
        current += step
    return values
