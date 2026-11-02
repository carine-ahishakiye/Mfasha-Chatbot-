#!/usr/bin/env python3
"""Compare retrievers on a labelled question file (columns: question, pid). Prints R@1, R@5, MRR@10.

    python scripts/evaluate_retrieval.py --questions data/sample/eval_questions.csv
"""
from __future__ import annotations

import argparse
import csv
import sys
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mfasha.config import Settings  # noqa: E402
from mfasha.factory import build_knowledge_base, build_retriever  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--questions", type=Path, default=Path("data/sample/eval_questions.csv"))
    parser.add_argument("--retrievers", nargs="+", default=["bm25", "tfidf", "hybrid"])
    args = parser.parse_args()

    settings = Settings.from_env()
    kb = build_knowledge_base(settings)
    with open(args.questions, encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))

    print(f"{len(rows)} questions, {len(kb)} passages")
    print(f"{'retriever':<12}{'R@1':>8}{'R@5':>8}{'MRR@10':>9}")
    for name in args.retrievers:
        retriever = build_retriever(replace(settings, retriever=name), kb)
        r1 = r5 = mrr = 0.0
        for row in rows:
            ranked = [h.passage.pid for h in retriever.search(row["question"], 10)]
            rank = ranked.index(row["pid"]) + 1 if row["pid"] in ranked else None
            r1 += rank == 1
            r5 += rank is not None and rank <= 5
            mrr += 1 / rank if rank else 0
        n = len(rows)
        print(f"{name:<12}{r1 / n:>8.3f}{r5 / n:>8.3f}{mrr / n:>9.3f}")


if __name__ == "__main__":
    main()
