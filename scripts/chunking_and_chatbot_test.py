# Locate project folders and data files

import sys
from pathlib import Path

here = Path(__file__).resolve().parent
ROOT = next((p for p in [here, *here.parents] if (p / "src").exists()), here)
sys.path.insert(0, str(ROOT / "src"))
import chatbot as cb

MODEL_DIR = cb.locate(ROOT, "kinya-retriever-e5", True) or cb.locate(ROOT, "kinya-retriever", True)
PASSAGES  = cb.locate(ROOT, "passages.jsonl")
QUERIES   = cb.locate(ROOT, "queries.jsonl")
PAIRS_DEV = cb.locate(ROOT, "pairs_dev.csv")

print("ROOT      :", ROOT)
print("MODEL_DIR :", MODEL_DIR)
print("PASSAGES  :", PASSAGES)
print("QUERIES   :", QUERIES)
print("PAIRS_DEV :", PAIRS_DEV)

#  Look for model.safetensors under ROOT

import os

skip = {".venv", "venv", ".git", "__pycache__", ".ipynb_checkpoints", "node_modules"}

print("Top-level items in ROOT:", sorted(p.name for p in ROOT.iterdir()))
print()
found = False
for cur, dirs, files in os.walk(ROOT):
    dirs[:] = [d for d in dirs if d not in skip]
    if "model.safetensors" in files:
        size = os.path.getsize(os.path.join(cur, "model.safetensors")) / 1e9
        print(f"model.safetensors: {size:.2f} GB  in  {cur}")
        found = True
    if "kinya" in os.path.basename(cur).lower():
        print("folder with 'kinya' in its name:", cur)
if not found:
    print("No model.safetensors found anywhere under ROOT")

# Check the retriever model folder is complete

MODEL_DIR = ROOT / "models"

need = ["model.safetensors", "config.json", "modules.json",
        "config_sentence_transformers.json", "sentence_bert_config.json",
        "tokenizer.json", "tokenizer_config.json"]

for n in need:
    print("OK      " if (MODEL_DIR / n).exists() else "MISSING ", n)

pool = MODEL_DIR / "1_Pooling"
print("OK      " if (pool / "config.json").exists() else "MISSING ", "1_Pooling/config.json")

others = sorted(p.name for p in MODEL_DIR.iterdir()
                if p.name not in need and p.name != "1_Pooling")
print("\nOther items in models:", others)

#  Load model, passages, queries and dev pairs

import numpy as np, pandas as pd, torch
from sentence_transformers import SentenceTransformer

DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
model = SentenceTransformer(str(MODEL_DIR), device=DEVICE)
model.max_seq_length = 256

passages = pd.read_json(open(PASSAGES, encoding="utf-8"), lines=True, dtype=False).astype(str)
queries  = pd.read_json(open(QUERIES,  encoding="utf-8"), lines=True, dtype=False).astype(str)
qid2text = dict(zip(queries.qid, queries.text))
passage_texts = passages.text.tolist()
pid2idx = {p: i for i, p in enumerate(passages.pid)}

pairs_dev = pd.read_csv(PAIRS_DEV, dtype=str)
dev_q = pairs_dev.qid.map(qid2text).tolist()
gold  = np.array([pid2idx[p] for p in pairs_dev.pos_pid])

print("device:", DEVICE)
print("passages:", len(passage_texts), "| dev questions:", len(dev_q))
v = model.encode(["soya ihunikwa ahantu hameze gute ?"], normalize_embeddings=True)
print("embedding size:", v.shape)

#  Token length statistics

tk = model.tokenizer
tok_lens  = np.array([len(tk.encode(t)) for t in passage_texts])
char_lens = np.array([len(t) for t in passage_texts])
cpt = char_lens.sum() / tok_lens.sum()

print("passages over 256 tokens:", int((tok_lens > 256).sum()), "of", len(tok_lens))
print("passages over 200 tokens:", int((tok_lens > 200).sum()))
print("median / max tokens     :", int(np.median(tok_lens)), "/", int(tok_lens.max()))
print("chars per token: %.2f  ->  200 tokens is about %d characters" % (cpt, 200 * cpt))

#  Split long passages into chunks
import re

MAX_TOKENS = 200
MAX_CHARS  = int(MAX_TOKENS * cpt)

def hard_split(sentence, max_chars):
    out, cur = [], ""
    for w in sentence.split():
        if cur and len(cur) + 1 + len(w) > max_chars:
            out.append(cur); cur = w
        else:
            cur = (cur + " " + w).strip()
    if cur: out.append(cur)
    return out

def split_passage(text, max_chars=MAX_CHARS):
    if len(text) <= max_chars:
        return [text]                                    # short passages stay whole
    sents = []
    for s in re.split(r"(?<=[.;?!])\s+", text):
        sents += hard_split(s, max_chars) if len(s) > max_chars else [s]
    chunks, cur = [], []
    for s in sents:
        if cur and len(" ".join(cur + [s])) > max_chars:
            chunks.append(" ".join(cur))
            cur = cur[-1:] if len(cur[-1]) < max_chars / 3 else []   # small overlap
        cur.append(s)
    if cur: chunks.append(" ".join(cur))
    return chunks

chunks = []
for pidx, (pid, text) in enumerate(zip(passages.pid, passage_texts)):
    for n, c in enumerate(split_passage(text)):
        chunks.append({"pid": pid, "pidx": pidx, "chunk_no": n, "text": c})

chunk_texts = [c["text"] for c in chunks]
chunk2p = np.array([c["pidx"] for c in chunks])
n_split = len(set(c["pidx"] for c in chunks if c["chunk_no"] > 0))
chunk_tokens = np.array([len(tk.encode(t)) for t in chunk_texts])

print(f"{len(passage_texts)} passages -> {len(chunks)} chunks | passages that were split: {n_split}")
print("chunks over 256 tokens:", int((chunk_tokens > 256).sum()), "| longest chunk:", int(chunk_tokens.max()), "tokens")

#  Encode passages, chunks and dev questions; save chunk files

import json
from pathlib import Path

DATA_DIR = Path(PASSAGES).parent

P = model.encode(passage_texts, batch_size=32, normalize_embeddings=True, show_progress_bar=True)
C = model.encode(chunk_texts,   batch_size=32, normalize_embeddings=True, show_progress_bar=True)
Q = model.encode(dev_q,         batch_size=32, normalize_embeddings=True, show_progress_bar=True)

with open(DATA_DIR / "chunks.jsonl", "w", encoding="utf-8") as f:
    for c in chunks:
        f.write(json.dumps(c, ensure_ascii=False) + "\n")
np.save(DATA_DIR / "chunk_emb_e5.npy", C)

print("shapes  passages:", P.shape, "| chunks:", C.shape, "| dev questions:", Q.shape)
print("saved to:", DATA_DIR)

#  Compare BM25 / embeddings / hybrid, whole passages vs chunks

from rank_bm25 import BM25Okapi

tok = cb.tok

def mm(S):                                   # row-wise min-max scaling
    mn, mx = S.min(1, keepdims=True), S.max(1, keepdims=True)
    return (S - mn) / (mx - mn + 1e-9)

def evaluate(S, name):
    g = S[np.arange(len(S)), gold][:, None]
    r = (S >= g).sum(1)
    return {"method": name,
            "Recall@1": (r <= 1).mean(), "Recall@5": (r <= 5).mean(),
            "Recall@10": (r <= 10).mean(),
            "MRR@10": np.where(r <= 10, 1 / r, 0).mean()}

def to_passage(S):                           
    out = np.full((S.shape[0], len(passage_texts)), -1e9)
    for p in np.unique(chunk2p):
        out[:, p] = S[:, chunk2p == p].max(1)
    return out

bm25_p = BM25Okapi([tok(t) for t in passage_texts])
bm25_c = BM25Okapi([tok(t) for t in chunk_texts])

S_emb_p = Q @ P.T
S_bm_p  = np.vstack([bm25_p.get_scores(tok(q)) for q in dev_q])
S_emb_c = Q @ C.T
S_bm_c  = np.vstack([bm25_c.get_scores(tok(q)) for q in dev_q])

rows = [
    evaluate(S_bm_p,                                  "BM25, whole passages"),
    evaluate(S_emb_p,                                 "Fine-tuned, whole passages"),
    evaluate(0.8 * mm(S_emb_p) + 0.2 * mm(S_bm_p),    "Hybrid 0.8, whole passages"),
    evaluate(to_passage(S_bm_c),                      "BM25, chunks"),
    evaluate(to_passage(S_emb_c),                     "Fine-tuned, chunks"),
    evaluate(to_passage(0.8 * mm(S_emb_c) + 0.2 * mm(S_bm_c)), "Hybrid 0.8, chunks"),
]
cmp = pd.DataFrame(rows).set_index("method")
print(cmp.round(3).to_string())
(ROOT / "results").mkdir(exist_ok=True)
cmp.round(4).to_csv(ROOT / "results" / "chunking_comparison_dev.csv")

#  Test the Chatbot class (Qdrant hybrid search) on dev questions

import time

bot = cb.Chatbot(chunks_path=DATA_DIR / "chunks.jsonl",
                 emb_path=DATA_DIR / "chunk_emb_e5.npy",
                 model=model)
print("chunks in database:", len(bot.chunks))

t0 = time.time()
h1 = h5 = 0
for q, g in zip(dev_q, pairs_dev.pos_pid):
    res, _ = bot.search(q, k=5)
    pids = [r["pid"] for r in res]
    h1 += (pids[0] == g)
    h5 += (g in pids)

print(f"Qdrant hybrid on dev  Recall@1: {h1/len(dev_q):.3f} | Recall@5: {h5/len(dev_q):.3f}")
print(f"time: {time.time()-t0:.0f} s for {len(dev_q)} questions ({(time.time()-t0)/len(dev_q):.2f} s each)")

#  Choose a refusal threshold using off-topic questions

off_topic = [
    "Ni gute nakora porogaramu ya telefoni?",
    "Ni nde wabaye perezida wa Amerika mu 2020?",
    "Ni gute nakwita ku mubiri wanjye ngo nkomere mu myitozo ya siporo?",
    "Ikibazo cy'ubukungu bw'u Buyapani ni ikihe?",
    "Ni gute nateka pizza?",
    "Ni iki cyiza cyo kureba kuri televiziyo uyu munsi?",
    "Ni gute nabona akazi muri banki?",
    "Ikipe y'umupira w'amaguru ya Arsenal yatsinze ryari?",
]

dev_conf = (Q @ C.T).max(1)
off_vecs = model.encode(off_topic, normalize_embeddings=True)
off_conf = (off_vecs @ C.T).max(1)

print("In-scope  : min %.3f | 5th pct %.3f | median %.3f" %
      (dev_conf.min(), np.percentile(dev_conf, 5), np.median(dev_conf)))
print("Off-topic :", np.round(np.sort(off_conf), 3))

rows = []
for t in (0.40, 0.45, 0.485, 0.50, 0.55, 0.60):
    rows.append({"threshold": t,
                 "real questions answered %": round(100 * (dev_conf >= t).mean(), 1),
                 "off-topic refused (of 8)": int((off_conf < t).sum())})
print(pd.DataFrame(rows).to_string(index=False))

# Try the chatbot on sample questions

bot.threshold = 0.485

tests = dev_q[:3] + off_topic[:3]
for q in tests:
    r = bot.ask(q)
    print(f"Q: {q}")
    print(f"   refused: {r['refused']} | confidence: {r['confidence']:.3f} | passage: {r['passage_id']}")
    print(f"   ANSWER (best chunk): {r['answer'][:400]}")
    if not r["refused"] and r.get("short"):
        print(f"   SHORT (2 best pieces): {r['short'][:300]}")

# does the soya passage mention equipment at all?
pid = bot.ask(dev_q[1])["passage_id"]
print("\nAll chunks of passage", pid, "for the question:", dev_q[1])
for c in bot.by_pid[pid]:
    print(f"[chunk {c['chunk_no']}] {cb.clean(c['text'])}\n")

# Build a review CSV

import random
random.seed(7)

# 25 dev questions spread over the different dev passages
by_p = pd.DataFrame({"i": range(len(gold)), "pid": pairs_dev.pos_pid.values}).groupby("pid")["i"].apply(list)
pools = [lst[:] for lst in by_p]
for lst in pools: random.shuffle(lst)
picked = []
while len(picked) < 25 and any(pools):
    for lst in pools:
        if lst and len(picked) < 25:
            picked.append(lst.pop())

my_questions = []   # optional: add your own farmer-style questions in Kinyarwanda here

rows = []
for i in picked:
    r = bot.ask(dev_q[i], short=False)
    rows.append({"type": "dev", "question": dev_q[i], "expected_pid": pairs_dev.pos_pid.iloc[i],
                 "returned_pid": r["passage_id"], "confidence": round(r["confidence"], 3),
                 "refused": r["refused"],
                 "top1_correct": (r["passage_id"] == pairs_dev.pos_pid.iloc[i]),
                 "answer": r["answer"]})
for q in off_topic:
    r = bot.ask(q, short=False)
    rows.append({"type": "off-topic", "question": q, "expected_pid": "REFUSE",
                 "returned_pid": r["passage_id"], "confidence": round(r["confidence"], 3),
                 "refused": r["refused"], "top1_correct": r["refused"], "answer": r["answer"]})
for q in my_questions:
    r = bot.ask(q, short=False)
    rows.append({"type": "mine", "question": q, "expected_pid": "", "returned_pid": r["passage_id"],
                 "confidence": round(r["confidence"], 3), "refused": r["refused"],
                 "top1_correct": "", "answer": r["answer"]})

rev = pd.DataFrame(rows)
rev["helpful_yes_partly_no"] = ""     
rev["notes"] = ""
rev.to_csv(ROOT / "results" / "chatbot_review.csv", index=False, encoding="utf-8-sig")

d = rev[rev.type == "dev"]; o = rev[rev.type == "off-topic"]
ans = d[~d.refused]
print(f"dev questions answered       : {len(ans)} of {len(d)}")
print(f"right passage when answered  : {int(ans.top1_correct.sum())} of {len(ans)}")
print(f"off-topic refused            : {int(o.refused.sum())} of {len(o)}")
print("\nWrong or refused dev questions:")
print(d[~d.top1_correct][["question", "confidence", "refused"]].to_string(index=False))

#Inspect wrong or refused answers

passage_by_pid = {str(p): t for p, t in zip(passages.pid, passages.text)}
wrong = d[~d.top1_correct]

for _, row in wrong.iterrows():
    res, _ = bot.search(row.question, k=5)
    pids = [x["pid"] for x in res]
    rank = pids.index(row.expected_pid) + 1 if row.expected_pid in pids else None
    print("Q:", row.question)
    print(f"   confidence {row.confidence} | expected passage is at rank: {rank}")
    print("   EXPECTED :", cb.clean(passage_by_pid.get(row.expected_pid, ""))[:300])
    print("   RETURNED :", cb.clean(passage_by_pid.get(row.returned_pid, ""))[:300])
ok, bad = d[d.top1_correct].confidence, d[~d.top1_correct].confidence
print(f"confidence when right: mean {ok.mean():.3f} | when wrong: mean {bad.mean():.3f}")

#  Confidence vs correctness

rows = []
for q, g in zip(dev_q, pairs_dev.pos_pid):
    res, conf = bot.search(q, k=5)
    pids = [r["pid"] for r in res]
    rows.append({"conf": conf, "rank": pids.index(g) + 1 if g in pids else 99})
ev = pd.DataFrame(rows)

print("Recall@1: %.3f | Recall@3: %.3f | Recall@5: %.3f" %
      ((ev["rank"] <= 1).mean(), (ev["rank"] <= 3).mean(), (ev["rank"] <= 5).mean()))
print()

bands = [(0.0, 0.6), (0.6, 0.7), (0.7, 0.8), (0.8, 2.0)]
out = []
for lo, hi in bands:
    sub = ev[(ev.conf >= lo) & (ev.conf < hi)]
    if len(sub):
        out.append({"confidence": f"{lo:.1f} to {min(hi,1):.1f}", "questions": len(sub),
                    "best answer correct %": round(100 * (sub["rank"] <= 1).mean(), 1),
                    "correct in top 3 %": round(100 * (sub["rank"] <= 3).mean(), 1)})
print(pd.DataFrame(out).to_string(index=False))