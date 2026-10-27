"""Scores the answer step on a bigger set than the notebook's 6 + 3 questions.

  python scripts/evaluate_answers.py                 # 40 farming questions from the test split + off-topic list
  python scripts/evaluate_answers.py --n-farming 80

Needs GROQ_API_KEY and the project assets. Writes results/answer_eval.csv and prints a summary.
The farming questions come from the *unseen-passage test split*, so they were never used for training.
Also prints the best-passage score for farming vs off-topic questions, to help you pick MIN_RETRIEVAL_SCORE.
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mfasha import config                                   # noqa: E402
from mfasha.llm import NO_ANSWER                            # noqa: E402
from mfasha.assets import ensure_assets                     # noqa: E402
from mfasha.pipeline import Mfasha                          # noqa: E402
from mfasha.retriever import Retriever                      # noqa: E402
from mfasha.text_utils import ungrounded_numbers, verbatim_share  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--n-farming", type=int, default=40)
ap.add_argument("--off-topic", default=str(config.ROOT / "eval" / "off_topic_rw.txt"))
ap.add_argument("--seed", type=int, default=42)
args = ap.parse_args()

ensure_assets()
bot = Mfasha(Retriever.load(), transcriber=None)            # typed questions only, no ASR needed

clean = config.ROOT / "data" / "clean"
split_csv, queries_jsonl = clean / "splits" / "test_unseen.csv", clean / "queries.jsonl"
if not (split_csv.exists() and queries_jsonl.exists()):
    sys.exit("Copy data/clean/splits/test_unseen.csv and data/clean/queries.jsonl from Drive to evaluate farming questions.")
qtext = {r["qid"]: r["text"] for r in map(json.loads, queries_jsonl.read_text(encoding="utf-8").splitlines())}
test = pd.read_csv(split_csv, dtype=str).sample(frac=1, random_state=args.seed).head(args.n_farming)
farming = [(qtext[r.qid], r.pos_pid) for r in test.itertuples() if r.qid in qtext]
off_topic = [l.strip() for l in Path(args.off_topic).read_text(encoding="utf-8").splitlines() if l.strip()]

rows = []
for kind, items in (("farming", farming), ("off_topic", [(q, None) for q in off_topic])):
    for q, gold in items:
        res = bot.ask(text=q)
        texts = [h.text for h in res.hits]
        refused = res.status == "refused"
        rows.append({
            "kind": kind, "question": q, "status": res.status, "answer": res.answer or "",
            "refused": refused, "guarded": res.guarded,
            "top_score": res.hits[0].score if res.hits else np.nan,
            "gold_in_top1": (res.hits[0].pid == gold) if gold and res.hits else None,
            "gold_in_top5": (gold in [h.pid for h in res.hits]) if gold else None,
            "verbatim_share": 1.0 if refused or not res.answer else verbatim_share(res.answer, texts),
            "numbers_not_in_passages": "" if refused or not res.answer else ", ".join(ungrounded_numbers(res.answer, texts)),
            "fluency_1to5": "", "faithful_1to5": "",          # fill in by hand for the report
        })
        print(f"[{kind}] {q[:60]} -> {res.status}")

df = pd.DataFrame(rows)
out = config.ROOT / "results" / "answer_eval.csv"
out.parent.mkdir(exist_ok=True)
df.to_csv(out, index=False)

f, o = df[df.kind == "farming"], df[df.kind == "off_topic"]
print("\n=== summary ===")
print(f"farming questions : {len(f)}")
print(f"  retrieval gold passage in top-1 / top-5 : {f.gold_in_top1.mean():.2f} / {f.gold_in_top5.mean():.2f}")
print(f"  wrongly refused                         : {f.refused.mean():.1%}")
print(f"  mean verbatim share (answered only)     : {f[~f.refused].verbatim_share.mean():.1%}")
print(f"  answers with numbers not in passages    : {(f.numbers_not_in_passages != '').mean():.1%}")
print(f"  number guard replaced the answer        : {f.guarded.mean():.1%}")
print(f"off-topic questions: {len(o)}")
print(f"  correctly refused                       : {o.refused.sum()} of {len(o)} ({o.refused.mean():.1%})")
print(f"best-passage score  farming median {f.top_score.median():.3f} (10th pct {f.top_score.quantile(.1):.3f}) | "
      f"off-topic median {o.top_score.median():.3f} (90th pct {o.top_score.quantile(.9):.3f})")
print("If the off-topic 90th percentile is below the farming 10th percentile, a MIN_RETRIEVAL_SCORE between them is safe.")
print("saved to", out)
