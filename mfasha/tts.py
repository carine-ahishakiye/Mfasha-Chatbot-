"""Text to speech with the stock MMS Kinyarwanda voice."""
import re

import numpy as np

from . import config
from .kin_numbers import speech_prep

PAUSE = {",": 0.25, ";": 0.3, ":": 0.3, ".": 0.5, "!": 0.5, "?": 0.5}


class Speaker:
    def __init__(self):
        import torch
        from transformers import AutoTokenizer, VitsModel

        self.torch = torch
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.tok = AutoTokenizer.from_pretrained(config.TTS_MODEL)
        self.model = VitsModel.from_pretrained(config.TTS_MODEL).to(self.device).eval()
        self.sr = int(self.model.config.sampling_rate)

    def _synth(self, clause: str) -> np.ndarray:
        clause = re.sub(r"[()\[\]\"]", " ", clause)
        clause = re.sub(r"\s+", " ", clause).strip()
        if len(re.findall(r"[a-z]", clause.lower())) < 2:        # nothing the voice can say
            return np.zeros(0, dtype=np.float32)
        inputs = self.tok(clause.lower(), return_tensors="pt").to(self.device)
        if inputs["input_ids"].shape[-1] < 2:
            return np.zeros(0, dtype=np.float32)
        self.torch.manual_seed(0)
        with self.torch.inference_mode():
            return self.model(**inputs).waveform[0].cpu().numpy()

    def speak(self, text: str):
        """One clause at a time with a short silence between, so it sounds like speech. Returns (wav, spoken_text)."""
        spoken = speech_prep(text)
        chunks, buffer = [], ""
        for piece in re.split(r"([,;:.!?])", spoken):
            if piece in PAUSE:
                if buffer.strip():
                    chunks.append(self._synth(buffer.strip()))
                    chunks.append(np.zeros(int(PAUSE[piece] * self.sr), dtype=np.float32))
                buffer = ""
            else:
                buffer += piece
        if buffer.strip():
            chunks.append(self._synth(buffer.strip()))
        wav = np.concatenate(chunks) if chunks else np.zeros(self.sr // 2, dtype=np.float32)
        return wav.astype(np.float32), spoken
