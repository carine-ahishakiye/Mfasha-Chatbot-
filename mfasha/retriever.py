
import json
from typing import List

import numpy as np

from . import config
from .interfaces import Hit, PassageSearcher


class Retriever(PassageSearcher):
    def __init__(self, passages, embeddings, encoder):
        assert len(passages) == len(embeddings), "passages and embeddings do not line up"
        self.passages = passages            # list of {"pid", "text"}
        self.P = embeddings.astype(np.float32)
        self.encoder = encoder              # function: str -> normalised float32 vector

    @classmethod
    def load(cls):
        import torch
        from sentence_transformers import SentenceTransformer

        passages = [json.loads(l) for l in config.PASSAGES_PATH.read_text(encoding="utf-8").splitlines() if l.strip()]
        device = "cuda" if torch.cuda.is_available() else "cpu"
        model = SentenceTransformer(str(config.E5_DIR), device=device)
        model.max_seq_length = config.MAX_SEQ_LEN

        P = np.load(config.PASSAGE_EMB) if config.PASSAGE_EMB.exists() else None
        if P is None or len(P) != len(passages):
            print("passage embeddings missing or out of date, computing them (slow on CPU) ...")
            P = model.encode([config.P_PREFIX + p["text"] for p in passages], batch_size=16,
                             normalize_embeddings=True, show_progress_bar=True)
            config.PASSAGE_EMB.parent.mkdir(parents=True, exist_ok=True)
            np.save(config.PASSAGE_EMB, P.astype(np.float32))

        def encode(q):
            return model.encode([config.Q_PREFIX + q], normalize_embeddings=True)[0].astype(np.float32)

        return cls(passages, P, encode)

    def search(self, question: str, k: int = None) -> List[Hit]:
        k = k or config.TOP_K
        scores = self.P @ self.encoder(question)
        top = np.argsort(-scores)[:k]
        return [Hit(self.passages[i]["pid"], self.passages[i]["text"], float(scores[i])) for i in top]
