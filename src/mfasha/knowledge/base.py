"""The verified knowledge base: passages, their categories and their review status."""
from __future__ import annotations

import csv
import json
from collections.abc import Iterable
from pathlib import Path
from typing import Optional

from mfasha.classification.keyword_labeler import CATEGORIES, GENERAL, KeywordCategoryLabeler
from mfasha.domain.errors import KnowledgeBaseError
from mfasha.domain.models import Passage


class KnowledgeBase:
    """Read-only collection of passages with lookup by id."""

    def __init__(self, passages: Iterable[Passage]):
        self._passages = list(passages)
        if not self._passages:
            raise KnowledgeBaseError("the knowledge base has no passages")
        self._by_id = {p.pid: p for p in self._passages}
        if len(self._by_id) != len(self._passages):
            raise KnowledgeBaseError("duplicate passage ids in the knowledge base")

    @property
    def passages(self) -> list[Passage]:
        return list(self._passages)

    def get(self, pid: str) -> Optional[Passage]:
        return self._by_id.get(pid)

    def __len__(self) -> int:
        return len(self._passages)

    def reviewed_count(self) -> int:
        return sum(p.reviewed for p in self._passages)


class KnowledgeBaseLoader:
    """Builds a KnowledgeBase from the files the notebook writes (`passages.jsonl`, the officer's
    `category_labels_officer.csv` and `officer_reviewed_passages.csv`)."""

    def __init__(self, labeler: KeywordCategoryLabeler | None = None, source: str = ""):
        self._labeler = labeler or KeywordCategoryLabeler()
        self._source = source

    def load(self, passages_path: Path, reviewed_path: Path | None = None,
             labels_path: Path | None = None) -> KnowledgeBase:
        passages_path = Path(passages_path)
        if not passages_path.exists():
            raise KnowledgeBaseError(f"knowledge base file not found: {passages_path}")

        reviewed = self._read_pid_column(reviewed_path) if reviewed_path else set()
        officer_labels = self._read_labels(labels_path) if labels_path else {}

        passages: list[Passage] = []
        with open(passages_path, encoding="utf-8") as handle:
            for line_no, line in enumerate(handle, start=1):
                if not line.strip():
                    continue
                try:
                    row = json.loads(line)
                    pid, text = str(row["pid"]), str(row["text"]).strip()
                except (json.JSONDecodeError, KeyError) as exc:
                    raise KnowledgeBaseError(f"{passages_path}:{line_no}: bad record ({exc})") from exc
                if not text:
                    continue
                category = officer_labels.get(pid) or row.get("category") or self._labeler.predict(text)
                if category not in CATEGORIES:
                    category = GENERAL
                passages.append(Passage(pid=pid, text=text, category=category,
                                        reviewed=pid in reviewed, source=row.get("source", self._source)))
        return KnowledgeBase(passages)

    @staticmethod
    def _read_pid_column(path: Path) -> set[str]:
        path = Path(path)
        if not path.exists():
            return set()
        with open(path, encoding="utf-8", newline="") as handle:
            return {str(r["pid"]).strip() for r in csv.DictReader(handle) if r.get("pid")}

    @staticmethod
    def _read_labels(path: Path) -> dict[str, str]:
        path = Path(path)
        if not path.exists():
            return {}
        with open(path, encoding="utf-8", newline="") as handle:
            return {str(r["pid"]).strip(): str(r["category"]).strip().lower()
                    for r in csv.DictReader(handle) if r.get("pid") and r.get("category")}
