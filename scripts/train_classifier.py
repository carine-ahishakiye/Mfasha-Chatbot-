#!/usr/bin/env python3
"""Train the TF-IDF question classifier (proposal 3.8 baseline) and save it to models/classifier.joblib.

    python scripts/train_classifier.py --train data/processed/questions_train.csv \
                                       --dev data/processed/questions_dev.csv
"""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sklearn.metrics import accuracy_score, precision_recall_fscore_support  # noqa: E402

from mfasha.classification import TfidfCategoryClassifier  # noqa: E402


def read(path: Path) -> tuple[list[str], list[str]]:
    with open(path, encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    return [r["question"] for r in rows], [r["category"] for r in rows]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--train", type=Path, required=True)
    parser.add_argument("--dev", type=Path, required=True)
    parser.add_argument("--out", type=Path, default=Path("models/classifier.joblib"))
    args = parser.parse_args()

    x_train, y_train = read(args.train)
    x_dev, y_dev = read(args.dev)
    best = None
    for kind, c in (("lr", 1), ("lr", 10), ("svm", 0.5), ("svm", 2)):       # same grid as the notebook
        model = TfidfCategoryClassifier(kind, c).fit(x_train, y_train)
        pred = model.predict_many(x_dev)
        _, _, f1, _ = precision_recall_fscore_support(y_dev, pred, average="macro", zero_division=0)
        print(f"{kind:>3} C={c:<4} dev accuracy {accuracy_score(y_dev, pred):.3f}  macro F1 {f1:.3f}")
        if best is None or f1 > best[0]:
            best = (f1, model, kind, c)
    best[1].save(args.out)
    print(f"saved the best ({best[2]}, C={best[3]}) to {args.out}")


if __name__ == "__main__":
    main()
