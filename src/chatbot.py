
import json
import os
import re
from pathlib import Path

import numpy as np

NO_ANSWER = ("Mbabarira, nta gisubizo nabonye. Gerageza kubaza ukundi, "
             "cyangwa ubaze umukozi w'ubuhinzi n'ubworozi.")
THRESHOLD = 0.485      # chosen on dev (refuses 6/8 off-topic, answers ~96% of real questions)
W_EMB = 0.8            # weight of the fine-tuned model in the hybrid (BM25 gets 0.2)

# confidence tiers, measured on the 196 dev questions:
#   >= 0.7        best answer correct ~94%   -> "high"
#   0.6 to 0.7    best answer correct 57%, right one in top 3: 86%  -> "medium"
#   below 0.6     best answer correct 30%, right one in top 3: 58%  -> "low"
CONF_HIGH = 0.70
CONF_MID = 0.60


def tier_of(confidence):
    if confidence >= CONF_HIGH:
        return "high"
    if confidence >= CONF_MID:
        return "medium"
    return "low"


# ----------------------------------------------------------------- text helpers
def tok(text):
    return re.findall(r"\w+", text.lower())


def minmax(x):
    x = np.asarray(x, dtype=float)
    return (x - x.min()) / (x.max() - x.min() + 1e-9)


def clean(text):
    """Fix the odd spacing in the dataset text (display only, never used for search)."""
    text = re.sub(r"%\s*\.\s*%", "%.", text)            # dataset quirk: "11 % . %"
    text = re.sub(r"\s+([,.;:!?%)])", r"\1", text)      # no space before punctuation
    text = re.sub(r"\(\s+", "(", text)                  # no space after "("
    text = re.sub(r"(\w)'\s+(\w)", r"\1'\2", text)      # n' amazi -> n'amazi
    return re.sub(r"\s+", " ", text).strip()


def segments(text, min_len=60):
    """Split list-style text into readable pieces (commas, colons and semicolons count)."""
    raw = re.split(r"(?<=[.?!;:,])\s+", text)
    segs, cur = [], ""
    for r in raw:
        cur = (cur + " " + r).strip()
        if len(cur) >= min_len:
            segs.append(cur)
            cur = ""
    if cur:
        if segs:
            segs[-1] += " " + cur
        else:
            segs.append(cur)
    return segs


# ----------------------------------------------------------------- file finding
def locate(root, name, want_dir=False):
    """Find a file or folder by name anywhere under root (skips .venv etc.)."""
    skip = {".venv", "venv", ".git", "__pycache__", ".ipynb_checkpoints", "node_modules"}
    for cur, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d not in skip]
        if want_dir:
            if name in dirs:
                return Path(cur) / name
        elif name in files:
            return Path(cur) / name
    return None


# ----------------------------------------------------------------- the chatbot
class Chatbot:
    COLLECTION = "kinya_agri_docs"

    def __init__(self, model_dir=None, chunks_path=None, emb_path=None,
                 threshold=THRESHOLD, w_emb=W_EMB, device="cpu", model=None):
        from qdrant_client import QdrantClient, models
        from rank_bm25 import BM25Okapi

        if model is None:                       # normal use: load the fine-tuned model
            from sentence_transformers import SentenceTransformer
            model = SentenceTransformer(str(model_dir), device=device)
            model.max_seq_length = 256
        self.model = model
        self.threshold = threshold
        self.w_emb = w_emb

        with open(chunks_path, encoding="utf-8") as f:
            self.chunks = [json.loads(line) for line in f if line.strip()]
        self.C = np.load(emb_path)
        assert len(self.chunks) == len(self.C), "chunks.jsonl and chunk_emb_e5.npy do not match"

        self.by_pid = {}
        for c in self.chunks:
            self.by_pid.setdefault(str(c["pid"]), []).append(c)

        self.bm25 = BM25Okapi([tok(c["text"]) for c in self.chunks])

        self.qc = QdrantClient(":memory:")      # rebuilt in a few seconds, nothing to manage
        self.qc.create_collection(
            self.COLLECTION,
            vectors_config=models.VectorParams(size=self.C.shape[1],
                                               distance=models.Distance.COSINE),
        )
        self.qc.upload_points(
            self.COLLECTION,
            points=[models.PointStruct(id=i, vector=self.C[i].tolist(), payload=self.chunks[i])
                    for i in range(len(self.chunks))],
            batch_size=256,
        )

    # -- encoding
    def encode(self, text):
        return np.asarray(self.model.encode([text], normalize_embeddings=True)[0])

    # -- hybrid search: Qdrant (dense) + BM25, best chunk per passage
    def search(self, question, k=5, pool=100):
        qv = self.encode(question)
        hits = self.qc.query_points(self.COLLECTION, query=qv.tolist(),
                                    limit=min(pool, len(self.chunks))).points
        ids = np.array([h.id for h in hits])
        dense = np.array([h.score for h in hits])
        bm = self.bm25.get_scores(tok(question))[ids]
        mix = self.w_emb * minmax(dense) + (1 - self.w_emb) * minmax(bm)

        best = {}
        for i, s in zip(ids, mix):
            pid = str(self.chunks[i]["pid"])
            if pid not in best or s > best[pid][0]:
                best[pid] = (float(s), int(i))
        top = sorted(best.values(), reverse=True)[:k]
        results = [{"score": s, "pid": str(self.chunks[i]["pid"]),
                    "chunk_id": i, "text": self.chunks[i]["text"]} for s, i in top]
        return results, float(dense.max())      # dense.max() = confidence used for refusing

    # -- answer a question
    def ask(self, question, short=False, n_segments=2):
        question = (question or "").strip()[:500]
        refusal = {"refused": True, "answer": NO_ANSWER, "short": NO_ANSWER, "confidence": 0.0,
                   "tier": "none", "passage_id": None, "alternatives": [], "sources": []}
        if not question:
            return refusal

        results, conf = self.search(question, k=3)
        if conf < self.threshold:
            return {**refusal, "confidence": conf}

        best = results[0]
        out = {"refused": False, "answer": clean(best["text"]), "short": None,
               "confidence": conf, "tier": tier_of(conf), "passage_id": best["pid"],
               # the other two candidates: the right one is in the top 3 for ~87% of dev questions
               "alternatives": [{"pid": r["pid"], "text": clean(r["text"])} for r in results[1:]],
               "sources": [{"pid": r["pid"], "score": r["score"]} for r in results]}

        if short:                      # optional, off by default: it was less reliable than the full chunk
            segs = [x for c in self.by_pid[best["pid"]] for x in segments(clean(c["text"]))]
            if len(segs) > n_segments:
                sv = np.asarray(self.model.encode(segs, normalize_embeddings=True))
                top = sorted(np.argsort(-(sv @ self.encode(question)))[:n_segments])
                out["short"] = " ".join(segs[i] for i in top)
            else:
                out["short"] = " ".join(segs)
        return out