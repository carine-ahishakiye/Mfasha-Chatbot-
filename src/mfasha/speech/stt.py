"""Speech-to-text. The notebook adopted facebook/mms-1b-all with the Kinyarwanda ("kin") adapter,
optionally fine-tuned (adapter weights saved under models/mms-kin-adapter)."""
from __future__ import annotations

from pathlib import Path

from mfasha.domain.errors import ServiceUnavailableError
from mfasha.interfaces import SpeechToText


class UnavailableSpeechToText(SpeechToText):
    """Null object used when STT is switched off: voice questions fail with a clear message."""

    name = "stt-unavailable"

    def __init__(self, reason: str = "speech-to-text is not enabled on this server"):
        self._reason = reason

    def transcribe(self, samples, sample_rate):
        raise ServiceUnavailableError(self._reason)


class MmsSpeechToText(SpeechToText):
    name = "mms-kin"

    def __init__(self, model_id: str = "facebook/mms-1b-all", language: str = "kin",
                 adapter_dir: Path | None = None, device: str | None = None):
        self._model_id, self._lang, self._adapter_dir, self._device_pref = model_id, language, adapter_dir, device
        self._processor = self._model = self._torch = None

    def _load(self):
        if self._model is not None:
            return
        try:
            import torch
            from transformers import AutoProcessor, Wav2Vec2ForCTC
        except ImportError as exc:  # pragma: no cover - depends on optional extra
            raise ServiceUnavailableError("transformers/torch not installed: pip install -r requirements-ml.txt") from exc
        self._torch = torch
        self._device = self._device_pref or ("cuda" if torch.cuda.is_available() else "cpu")
        self._processor = AutoProcessor.from_pretrained(self._model_id, target_lang=self._lang)
        self._model = Wav2Vec2ForCTC.from_pretrained(
            self._model_id, target_lang=self._lang, ignore_mismatched_sizes=True).to(self._device).eval()
        if self._adapter_dir and Path(self._adapter_dir).exists():
            self._load_fine_tuned_adapter(Path(self._adapter_dir))

    def _load_fine_tuned_adapter(self, adapter_dir: Path) -> None:
        for candidate in sorted(adapter_dir.glob("*.pt")) + sorted(adapter_dir.glob("*.bin")):
            state = self._torch.load(candidate, map_location=self._device)
            self._model.load_state_dict(state, strict=False)
            return

    def transcribe(self, samples, sample_rate: int) -> str:
        self._load()
        inputs = self._processor(samples, sampling_rate=sample_rate, return_tensors="pt").to(self._device)
        with self._torch.no_grad():
            logits = self._model(**inputs).logits
        ids = self._torch.argmax(logits, dim=-1)[0]
        return self._processor.decode(ids).strip()
