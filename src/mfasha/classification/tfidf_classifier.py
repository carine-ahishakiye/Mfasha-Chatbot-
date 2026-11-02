
from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import joblib
from scipy.sparse import hstack
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.svm import LinearSVC

from mfasha.interfaces import Classifier


class TfidfCategoryClassifier(Classifier):
    name = "tfidf-classifier"

    def __init__(self, model: str = "svm", c: float = 1.0):
        if model not in {"svm", "lr"}:
            raise ValueError("model must be 'svm' or 'lr'")
        self._kind, self._c = model, c
        self._word = TfidfVectorizer(analyzer="word", ngram_range=(1, 2), token_pattern=r"[\w']+",
                                     sublinear_tf=True, min_df=1)
        self._char = TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 5), sublinear_tf=True, min_df=1)
        self._model = None

    def _features(self, texts: Sequence[str]):
        return hstack([self._word.transform(texts), self._char.transform(texts)]).tocsr()

    def fit(self, texts: Sequence[str], labels: Sequence[str]) -> TfidfCategoryClassifier:
        if len(set(labels)) < 2:
            raise ValueError("need at least two different categories to train a classifier")
        self._word.fit(texts)
        self._char.fit(texts)
        estimator = (LogisticRegression(max_iter=2000, C=self._c, class_weight="balanced")
                     if self._kind == "lr" else LinearSVC(C=self._c, class_weight="balanced"))
        self._model = estimator.fit(self._features(texts), labels)
        return self

    def predict(self, text: str) -> str:
        return self.predict_many([text])[0]

    def predict_many(self, texts: Sequence[str]) -> list[str]:
        if self._model is None:
            raise RuntimeError("classifier is not trained: call fit() or load() first")
        return [str(p) for p in self._model.predict(self._features(texts))]

    # persistence 
    def save(self, path: Path) -> None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        joblib.dump({"word": self._word, "char": self._char, "model": self._model, "kind": self._kind}, path)

    @classmethod
    def load(cls, path: Path) -> TfidfCategoryClassifier:
        blob = joblib.load(path)
        obj = cls(model=blob.get("kind", "svm"))
        # notebook files use the keys vec_w / vec_c, files saved by save() use word / char
        obj._word = blob.get("word", blob.get("vec_w"))
        obj._char = blob.get("char", blob.get("vec_c"))
        obj._model = blob["model"]
        return obj
