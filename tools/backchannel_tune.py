"""离线网格调参:用接话 embedding 模型对评测集编码一次,缓存分数后穷举
threshold × margin,输出准确率最优点。

用法:
    python tools/backchannel_tune.py data/backchannel_eval.jsonl

评测集是 data/backchannel_eval.jsonl(debug 开关下自动积累),每行需人工
补上 "gold_intent"(正确意图,或 null 表示本不该接话)后才参与评估;
未标注的行会被跳过。模型与原型走与运行时相同的本地缓存。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from app.backchannel.embedding_classifier import (  # noqa: E402
    DEFAULT_INTENT_MARGIN,
    DEFAULT_INTENT_THRESHOLD,
    EmbeddingIntentClassifier,
)
from app.backchannel.model_cache import backchannel_model_cache_kwargs  # noqa: E402
from app.backchannel.prototypes import load_runtime_intent_prototypes  # noqa: E402
from app.backchannel.tuning import ScoredExample, evaluate_point, frange, sweep  # noqa: E402


def _load_eval_rows(path: Path) -> list[dict]:
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict) and "gold_intent" in row and row.get("text"):
            rows.append(row)
    return rows


def _build_scored_examples(rows: list[dict], base_dir: Path) -> list[ScoredExample]:
    classifier = EmbeddingIntentClassifier(
        prototypes=load_runtime_intent_prototypes(base_dir),
        model_kwargs=backchannel_model_cache_kwargs(base_dir),
    )
    # 借用内部编码 + 原型向量得到 per-intent 排序分(与运行时同源)。
    prototype_vectors = classifier._ensure_prototype_vectors()  # noqa: SLF001
    if not prototype_vectors:
        raise SystemExit("无法加载接话模型或原型,先在设置页安装模型。")

    examples: list[ScoredExample] = []
    for row in rows:
        vector = classifier._encode_one(str(row["text"]))  # noqa: SLF001
        if vector is None:
            continue
        ranked = []
        for intent, vectors in prototype_vectors.items():
            best = max(
                (classifier_cosine(vector, proto) for proto in vectors),
                default=-1.0,
            )
            ranked.append((intent, best))
        ranked.sort(key=lambda item: item[1], reverse=True)
        examples.append(
            ScoredExample(
                text=str(row["text"]),
                gold_intent=row.get("gold_intent"),
                ranked=tuple(ranked),
            )
        )
    return examples


def classifier_cosine(left, right) -> float:
    from app.backchannel.embedding_classifier import _cosine

    return _cosine(left, right)


def main() -> None:
    parser = argparse.ArgumentParser(description="接话意图阈值离线网格调参")
    parser.add_argument("eval_path", type=Path, help="评测集 jsonl(含人工标注 gold_intent)")
    parser.add_argument("--base-dir", type=Path, default=_PROJECT_ROOT)
    parser.add_argument("--thr", nargs=3, type=float, default=(0.70, 0.95, 0.01), metavar=("LO", "HI", "STEP"))
    parser.add_argument("--margin", nargs=3, type=float, default=(0.00, 0.20, 0.01), metavar=("LO", "HI", "STEP"))
    parser.add_argument("--top", type=int, default=10)
    args = parser.parse_args()

    rows = _load_eval_rows(args.eval_path)
    if not rows:
        raise SystemExit("评测集没有已标注 gold_intent 的样本。")
    print(f"已标注样本:{len(rows)} 条;编码中(首次会冷加载模型)……")
    examples = _build_scored_examples(rows, args.base_dir)

    thresholds = frange(*args.thr)
    margins = frange(*args.margin)
    points = sweep(examples, thresholds, margins)
    current = evaluate_point(examples, DEFAULT_INTENT_THRESHOLD, DEFAULT_INTENT_MARGIN)

    print(f"\n网格 {len(thresholds)}×{len(margins)} = {len(points)} 点")
    print(
        f"当前默认 thr={DEFAULT_INTENT_THRESHOLD} margin={DEFAULT_INTENT_MARGIN}: "
        f"acc={current.accuracy:.3f} 直采={current.direct} 错={current.wrong} 弃权={current.abstained}"
    )
    print(f"\n最优 {args.top} 点(acc↓ 错采↓ 弃权↓):")
    for point in points[: args.top]:
        print(
            f"  thr={point.threshold:.2f} margin={point.margin:.2f}  "
            f"acc={point.accuracy:.3f} 直采={point.direct} 错={point.wrong} 弃权={point.abstained}"
        )


if __name__ == "__main__":
    main()
