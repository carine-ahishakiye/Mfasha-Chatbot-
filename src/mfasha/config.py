"""Settings read from environment variables (12-factor style). One object, built once, passed down."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_REFERRAL_MESSAGE = ("Mbabarira, nta gisubizo cyizewe mfite kuri iki kibazo. "
                            "Nyamuneka baza agoronome w'umurenge wawe.")


def _flag(name: str, default: bool) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    # data
    knowledge_path: Path = ROOT / "data" / "sample" / "passages.jsonl"
    reviewed_path: Path | None = ROOT / "data" / "sample" / "officer_reviewed_passages.csv"
    labels_path: Path | None = None
    models_dir: Path = ROOT / "models"
    database_url: str = f"sqlite:///{ROOT / 'mfasha.db'}"

    # retrieval and classification
    retriever: str = "hybrid"                # bm25 | tfidf | hybrid | embedding
    embedding_model: str = "intfloat/multilingual-e5-large"
    top_k: int = 5

    # referral rule (overridden by models/referral_threshold.json when the notebook wrote one)
    referral_threshold: float = 0.20
    referral_margin: float = 0.02
    use_agreement: bool = True
    serve_unreviewed: bool = False
    referral_message: str = DEFAULT_REFERRAL_MESSAGE

    # speech
    enable_stt: bool = False
    enable_tts: bool = False
    stt_model: str = "facebook/mms-1b-all"
    stt_language: str = "kin"
    tts_model: str = "facebook/mms-tts-kin"

    # api
    api_key: str = ""                        # empty = officer/admin endpoints are disabled
    max_question_chars: int = 500
    max_audio_bytes: int = 5_000_000
    max_audio_seconds: float = 30.0
    cors_origins: tuple[str, ...] = ("*",)

    @classmethod
    def from_env(cls) -> Settings:
        d = cls()
        path = lambda name, default: Path(os.environ[name]) if os.getenv(name) else default  # noqa: E731
        settings = replace(
            d,
            knowledge_path=path("MFASHA_KNOWLEDGE_PATH", d.knowledge_path),
            reviewed_path=path("MFASHA_REVIEWED_PATH", d.reviewed_path),
            labels_path=path("MFASHA_LABELS_PATH", d.labels_path),
            models_dir=path("MFASHA_MODELS_DIR", d.models_dir),
            database_url=os.getenv("DATABASE_URL", d.database_url),
            retriever=os.getenv("MFASHA_RETRIEVER", d.retriever),
            embedding_model=os.getenv("MFASHA_EMBEDDING_MODEL", d.embedding_model),
            referral_threshold=float(os.getenv("MFASHA_REFERRAL_THRESHOLD", d.referral_threshold)),
            referral_margin=float(os.getenv("MFASHA_REFERRAL_MARGIN", d.referral_margin)),
            use_agreement=_flag("MFASHA_USE_AGREEMENT", d.use_agreement),
            serve_unreviewed=_flag("MFASHA_SERVE_UNREVIEWED", d.serve_unreviewed),
            enable_stt=_flag("MFASHA_ENABLE_STT", d.enable_stt),
            enable_tts=_flag("MFASHA_ENABLE_TTS", d.enable_tts),
            stt_model=os.getenv("MFASHA_STT_MODEL", d.stt_model),
            tts_model=os.getenv("MFASHA_TTS_MODEL", d.tts_model),
            api_key=os.getenv("MFASHA_API_KEY", d.api_key),
            cors_origins=tuple(os.getenv("MFASHA_CORS_ORIGINS", "*").split(",")),
        )
        return settings.with_tuned_referral()

    def with_tuned_referral(self) -> Settings:
        """Use the threshold the notebook tuned on validation data when its JSON file is present."""
        tuned = self.models_dir / "referral_threshold.json"
        if not tuned.exists():
            return self
        data = json.loads(tuned.read_text(encoding="utf-8"))
        return replace(self, referral_threshold=float(data.get("threshold", self.referral_threshold)),
                       referral_margin=float(data.get("margin", self.referral_margin)),
                       use_agreement=bool(data.get("use_agreement", self.use_agreement)))
