import json

import pytest

from mfasha.classification import KeywordCategoryLabeler, TfidfCategoryClassifier
from mfasha.domain.errors import KnowledgeBaseError
from mfasha.knowledge import KnowledgeBase, KnowledgeBaseLoader


def test_keyword_labeler_examples():
    label = KeywordCategoryLabeler().predict
    assert label("Guhinga ibigori: ibigori bitera neza") == "crop production"
    assert label("Nkunganire ku mbuto: leta itanga nkunganire") == "agricultural programmes"
    assert label("Iteganyagihe n'ubuhinzi: imvura nyinshi") == "weather-related farming"


def test_tfidf_classifier_learns_and_round_trips(tmp_path):
    texts = ["ibigori bitera", "ibishyimbo bitera", "inka zikenera amazi", "inkoko zikenera amazi"]
    labels = ["crop production", "crop production", "livestock management", "livestock management"]
    clf = TfidfCategoryClassifier("lr").fit(texts, labels)
    assert clf.predict("ibigori") == "crop production"
    clf.save(tmp_path / "c.joblib")
    assert TfidfCategoryClassifier.load(tmp_path / "c.joblib").predict("inka") == "livestock management"


def test_classifier_needs_two_classes_and_training():
    with pytest.raises(ValueError):
        TfidfCategoryClassifier().fit(["a", "b"], ["x", "x"])
    with pytest.raises(RuntimeError):
        TfidfCategoryClassifier().predict("a")


def test_loader_reads_reviewed_and_officer_labels(tmp_path):
    (tmp_path / "p.jsonl").write_text(
        json.dumps({"pid": "1", "text": "Guhinga ibigori: x"}) + "\n" + json.dumps({"pid": "2", "text": "Korora inka: y"}) + "\n",
        encoding="utf-8")
    (tmp_path / "r.csv").write_text("pid,reviewer\n1,Officer\n", encoding="utf-8")
    (tmp_path / "l.csv").write_text("pid,category\n2,animal health\n", encoding="utf-8")
    kb = KnowledgeBaseLoader().load(tmp_path / "p.jsonl", tmp_path / "r.csv", tmp_path / "l.csv")
    assert kb.get("1").reviewed and not kb.get("2").reviewed
    assert kb.get("2").category == "animal health"          # the officer's label wins over the draft


def test_loader_errors(tmp_path):
    with pytest.raises(KnowledgeBaseError):
        KnowledgeBaseLoader().load(tmp_path / "missing.jsonl")
    (tmp_path / "bad.jsonl").write_text("{not json}\n", encoding="utf-8")
    with pytest.raises(KnowledgeBaseError):
        KnowledgeBaseLoader().load(tmp_path / "bad.jsonl")
    with pytest.raises(KnowledgeBaseError):
        KnowledgeBase([])
