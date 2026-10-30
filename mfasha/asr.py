
import numpy as np

from . import config
from .interfaces import SpeechRecognizer


class Transcriber(SpeechRecognizer):
    def __init__(self):
        import torch
        from transformers import AutoProcessor, Wav2Vec2ForCTC

        self.torch = torch
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.proc = AutoProcessor.from_pretrained(config.ASR_MODEL, target_lang=config.ASR_LANG)
        model = Wav2Vec2ForCTC.from_pretrained(config.ASR_MODEL, target_lang=config.ASR_LANG,
                                               ignore_mismatched_sizes=True)
        state = torch.load(config.ASR_ADAPTER, map_location="cpu")
        result = model.load_state_dict(state, strict=False)
        # the file only holds the adapter and output layer, so nothing in it may be unknown to the model
        assert not result.unexpected_keys, f"adapter file does not fit the model: {result.unexpected_keys[:3]}"
        print(f"ASR: loaded {len(state)} fine-tuned tensors")
        self.model = model.to(self.device).eval()

    def transcribe(self, audio: np.ndarray) -> str:
        """audio: float32 mono at 16 kHz."""
        torch = self.torch
        max_len = config.MAX_AUDIO_SECONDS * config.ASR_SR
        audio = np.asarray(audio, dtype=np.float32)[:max_len]
        if len(audio) < config.ASR_SR // 4:          # under a quarter of a second
            return ""
        x = self.proc.feature_extractor(audio, sampling_rate=config.ASR_SR,
                                        return_tensors="pt").input_values.to(self.device)
        with torch.inference_mode():
            if self.device == "cuda":
                with torch.autocast("cuda", dtype=torch.float16):
                    logits = self.model(input_values=x).logits
            else:
                logits = self.model(input_values=x).logits
        return self.proc.decode(logits.argmax(-1)[0]).strip()
