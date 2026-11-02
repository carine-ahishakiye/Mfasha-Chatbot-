#!/usr/bin/env python3
"""Download kinya-ag-retrieval and write the clean files MFASHA needs (notebook cell 2, as a script).

    python scripts/prepare_data.py --out data/processed

Outputs
    passages.jsonl       knowledge base: pid, text, draft category
    questions_<split>.csv  question, pid, category   (train / dev / test, for the classifier and evaluation)
    category_labels_draft.csv  give this to an agricultural officer to correct (proposal section 3.6)
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mfasha.classification.keyword_labeler import KeywordCategoryLabeler  # noqa: E402
from mfasha.nlp.preprocessing import TextCleaner  # noqa: E402

REPO = "C4IR-RW/kinya-ag-retrieval"


def heading_only(text: str) -> bool:
    """True for passages that are only a title (nothing for a farmer to read)."""
    if ":" not in text:
        return len(re.findall(r"\w", text)) < 10
    return len(re.findall(r"\w", text.split(":", 1)[1])) == 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", type=Path, default=Path("data/processed"))
    args = parser.parse_args()

    try:
        from huggingface_hub import hf_hub_download
    except ImportError:
        sys.exit("pip install huggingface_hub  (and set HF_TOKEN if the dataset is gated)")

    def lines(name: str, keep_blank: bool = False) -> list[str]:
        with open(hf_hub_download(REPO, name, repo_type="dataset"), encoding="utf-8") as f:
            rows = [line.strip().strip('"') for line in f]
        return rows if keep_blank else [r for r in rows if r]

    cleaner, labeler = TextCleaner(strip_greeting=False), KeywordCategoryLabeler()
    pids, raw = lines("rw_ag_retrieval_passage_id.txt"), lines("rw_ag_retrieval_passage_text.txt")
    assert len(pids) == len(raw), "passage ids and texts do not line up"
    qids, qraw = lines("rw_ag_retrieval_query_id.txt", True), lines("rw_ag_retrieval_query_text.txt", True)
    assert len(qids) == len(qraw), "query ids and texts do not line up"

    passages = {p: cleaner.clean(t) for p, t in zip(pids, raw, strict=True)}
    passages = {p: t for p, t in passages.items() if not heading_only(t)}
    category = {p: labeler.predict(t) for p, t in passages.items()}
    questions = {q: cleaner.clean(t) for q, t in zip(qids, qraw, strict=True) if q}

    args.out.mkdir(parents=True, exist_ok=True)
    with open(args.out / "passages.jsonl", "w", encoding="utf-8") as f:
        for pid, text in passages.items():
            f.write(json.dumps({"pid": pid, "text": text, "category": category[pid]}, ensure_ascii=False) + "\n")
    with open(args.out / "category_labels_draft.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["pid", "category", "text_start", "officer_category"])
        w.writerows([pid, category[pid], passages[pid][:100], ""] for pid in passages)

    for split in ("train", "dev", "test"):
        path = hf_hub_download(REPO, f"rw_ag_retrieval_qpntriplets_{split}.tsv", repo_type="dataset")
        seen, rows = set(), []
        with open(path, encoding="utf-8") as f:
            for line in f:
                parts = line.rstrip("\n").split("\t")
                if len(parts) < 2 or parts[0] not in questions or parts[1] not in passages:
                    continue
                if (parts[0], parts[1]) in seen:
                    continue
                seen.add((parts[0], parts[1]))
                rows.append([questions[parts[0]], parts[1], category[parts[1]]])
        with open(args.out / f"questions_{split}.csv", "w", encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            w.writerow(["question", "pid", "category"])
            w.writerows(rows)
        print(f"{split}: {len(rows)} question-passage pairs")
    print(f"{len(passages)} passages written to {args.out}")


if __name__ == "__main__":
    main()
