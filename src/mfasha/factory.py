"""Composition root: the only place that knows which concrete classes are used.

Everything else receives its collaborators through constructors (Dependency Injection), which is what
lets the tests build a pipeline from fakes and lets the proposal's "baseline or pretrained" decision be a
configuration value.
"""
from __future__ import annotations

import logging

from mfasha.classification.keyword_labeler import KeywordCategoryLabeler
from mfasha.classification.tfidf_classifier import TfidfCategoryClassifier
from mfasha.config import Settings
from mfasha.interfaces import Classifier, Retriever, SpeechToText, TextToSpeech
from mfasha.knowledge.base import KnowledgeBase, KnowledgeBaseLoader
from mfasha.nlp.preprocessing import TextCleaner
from mfasha.pipeline import MfashaPipeline
from mfasha.referral.policy import ReferralPolicy
from mfasha.retrieval import BM25Retriever, HybridRetriever, TfidfRetriever
from mfasha.speech.stt import MmsSpeechToText, UnavailableSpeechToText
from mfasha.speech.tts import MmsTextToSpeech, UnavailableTextToSpeech

log = logging.getLogger(__name__)


def build_knowledge_base(settings: Settings) -> KnowledgeBase:
    return KnowledgeBaseLoader(source="C4IR-RW/kinya-ag-retrieval").load(
        settings.knowledge_path, settings.reviewed_path, settings.labels_path)


def build_retriever(settings: Settings, kb: KnowledgeBase) -> Retriever:
    kind = settings.retriever
    if kind == "bm25":
        retriever: Retriever = BM25Retriever()
    elif kind == "tfidf":
        retriever = TfidfRetriever()
    elif kind == "hybrid":
        retriever = HybridRetriever([BM25Retriever(), TfidfRetriever()], weights=[0.6, 0.4])
    elif kind == "embedding":
        from mfasha.retrieval.embedding import EmbeddingRetriever  # lazy: needs the ML extra
        best = settings.models_dir / "kinya-e5-large" / "best"
        retriever = EmbeddingRetriever(str(best if best.exists() else settings.embedding_model),
                                       cache_dir=settings.models_dir / "cache")
    else:
        raise ValueError(f"unknown retriever '{kind}' (use bm25, tfidf, hybrid or embedding)")
    retriever.index(kb.passages)
    return retriever


def build_classifier(settings: Settings, kb: KnowledgeBase) -> Classifier:
    trained = settings.models_dir / "classifier.joblib"
    if trained.exists():
        return TfidfCategoryClassifier.load(trained)
    labels = [p.category for p in kb.passages]
    if len(set(labels)) >= 2 and len(kb) >= 8:          # train quickly on the passages themselves
        log.warning("no trained classifier at %s: training a small one on the knowledge base", trained)
        return TfidfCategoryClassifier(model="svm").fit([p.text for p in kb.passages], labels)
    return KeywordCategoryLabeler()


def build_stt(settings: Settings) -> SpeechToText:
    if not settings.enable_stt:
        return UnavailableSpeechToText()
    return MmsSpeechToText(settings.stt_model, settings.stt_language,
                           adapter_dir=settings.models_dir / "mms-kin-adapter")


def build_tts(settings: Settings) -> TextToSpeech:
    if not settings.enable_tts:
        return UnavailableTextToSpeech()
    tuned = settings.models_dir / "mms-tts-kin-ft2"
    return MmsTextToSpeech(str(tuned if tuned.exists() else settings.tts_model))


def build_pipeline(settings: Settings, kb: KnowledgeBase | None = None) -> tuple[MfashaPipeline, KnowledgeBase]:
    kb = kb or build_knowledge_base(settings)
    policy = ReferralPolicy.standard(settings.referral_threshold, settings.referral_margin,
                                     settings.use_agreement, settings.serve_unreviewed)
    pipeline = MfashaPipeline(
        cleaner=TextCleaner(), classifier=build_classifier(settings, kb),
        retriever=build_retriever(settings, kb), policy=policy,
        stt=build_stt(settings), tts=build_tts(settings),
        referral_message=settings.referral_message, top_k=settings.top_k,
        source="C4IR-RW/kinya-ag-retrieval")
    return pipeline, kb
