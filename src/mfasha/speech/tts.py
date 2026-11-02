"""Text-to-speech. The notebook fine-tuned the MMS Kinyarwanda VITS voice on kinya-ag-tts; the folder
it saves (models/mms-tts-kin-ft2) is loaded here. Falls back to the public facebook/mms-tts-kin."""
from __future__ import annotations

from mfasha.domain.errors import ServiceUnavailableError
from mfasha.interfaces import TextToSpeech
from mfasha.speech.audio import encode_wav


class UnavailableTextToSpeech(TextToSpeech):
    name = "tts-unavailable"

    def synthesize(self, text):
        raise ServiceUnavailableError("text-to-speech is not enabled on this server")


class MmsTextToSpeech(TextToSpeech):
    name = "mms-tts-kin"

    def __init__(self, model_path: str = "facebook/mms-tts-kin", device: str | None = None):
        self._model_path, self._device_pref = model_path, device
        self._tokenizer = self._model = self._torch = None

    def _load(self):
        if self._model is not None:
            return
        try:
            import torch
            from transformers import AutoTokenizer, VitsModel
        except ImportError as exc:  # pragma: no cover - depends on optional extra
            raise ServiceUnavailableError("transformers/torch not installed: pip install -r requirements-ml.txt") from exc
        self._torch = torch
        self._device = self._device_pref or ("cuda" if torch.cuda.is_available() else "cpu")
        self._tokenizer = AutoTokenizer.from_pretrained(self._model_path)
        self._model = VitsModel.from_pretrained(self._model_path).to(self._device).eval()

    def synthesize(self, text: str) -> bytes:
        self._load()
        inputs = self._tokenizer(text, return_tensors="pt").to(self._device)
        with self._torch.no_grad():
            waveform = self._model(**inputs).waveform[0].cpu().numpy()
        return encode_wav(waveform, self._model.config.sampling_rate)
