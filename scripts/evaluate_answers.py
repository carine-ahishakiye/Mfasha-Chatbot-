"""Scores the answer step: does the top passage get shown for farming questions and referred for off-topic ones?

  python scripts/evaluate_answers.py                 # 40 farming questions from the test split + off-topic list
  python scripts/evaluate_answers.py --n-farming 80

No API key is needed. Needs the project assets. Writes results/answer_eval.csv and prints a summary.
The farming questions come from the *unseen-passage test split*, so they were never used for training.
Also prints the best-passage score for farming vs off-topic questions, to check the referral threshold.
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mfasha import config                                   # noqa: E402
from mfasha.assets import ensure_assets                     # noqa: E402
from mfasha.pipeline import ANSWERED, Mfasha                # noqa: E402
from mfasha.retriever import Retriever                      # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--n-farming", type=int, default=40)
ap.add_argument("--off-topic", default=str(config.ROOT / "eval" / "off_topic_rw.txt"))
ap.add_argument("--seed", type=int, default=42)
args = ap.parse_args()

ensure_assets()
bot = Mfasha(Retriever.load(), transcriber=None)            # typed questions only, no ASR needed
print(f"referral threshold: {bot.threshold:.4f}" + ("" if bot.threshold else "  (0 = off-topic questions are never referred)"))

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
        rows.append({
            "kind": kind, "question": q, "status": res.status, "referral_reason": res.referral_reason,
            "referred": res.status != ANSWERED, "passage_id": res.hits[0].pid if res.hits else None,
            "top_score": res.score if res.score is not None else np.nan,
            "gold_in_top1": (res.hits[0].pid == gold) if gold and res.hits else None,
            "gold_in_top5": (gold in [h.pid for h in res.hits]) if gold else None,
        })
        print(f"[{kind}] {q[:60]} -> {res.status}")

df = pd.DataFrame(rows)
out = config.ROOT / "results" / "answer_eval.csv"
out.parent.mkdir(exist_ok=True)
df.to_csv(out, index=False)

f, o = df[df.kind == "farming"], df[df.kind == "off_topic"]
shown = f[~f.referred]
print("\n=== summary ===")
print(f"farming questions : {len(f)}")
print(f"  retrieval gold passage in top-1 / top-5 : {f.gold_in_top1.mean():.2f} / {f.gold_in_top5.mean():.2f}")
print(f"  answered                                : {(~f.referred).mean():.1%}")
print(f"  right passage among answered            : {shown.gold_in_top1.mean():.1%}" if len(shown) else "  nothing answered")
print(f"  wrongly referred                        : {f.referred.mean():.1%}")
print(f"off-topic questions: {len(o)}")
print(f"  correctly referred                      : {o.referred.sum()} of {len(o)} ({o.referred.mean():.1%})")
print(f"best-passage score  farming median {f.top_score.median():.3f} (10th pct {f.top_score.quantile(.1):.3f}) | "
      f"off-topic median {o.top_score.median():.3f} (90th pct {o.top_score.quantile(.9):.3f})")
print("If the off-topic 90th percentile is below the farming 10th percentile, a threshold between them separates the two groups cleanly.")
print("saved to", out)
