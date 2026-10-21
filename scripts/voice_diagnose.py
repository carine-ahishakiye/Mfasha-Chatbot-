"""Find out WHY voice is slow: first call only, or every call?

Run from the project folder, with server.py stopped:
    python scripts/voice_diagnose.py          (voice output only, a few minutes)
    python scripts/voice_diagnose.py asr      (also times speech recognition, slower)
"""
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, "src")
import torch  # noqa: E402

print("python", sys.version.split()[0], "| torch", torch.__version__)
print("logical CPU cores:", os.cpu_count(), "| torch threads:", torch.get_num_threads())
try:
    import psutil
    vm = psutil.virtual_memory()
    print(f"RAM total {vm.total / 1e9:.1f} GB | free now {vm.available / 1e9:.1f} GB")
except ImportError:
    print("(run: pip install psutil   to also see the RAM numbers)")

a = torch.randn(2000, 2000)
t = time.time()
for _ in range(10):
    a @ a
print("CPU matmul test: %.1f s   (a normal laptop: about 1 to 5 s)" % (time.time() - t), flush=True)

import tts  # noqa: E402

t = time.time()
tts.load()
print("TTS load: %.1f s" % (time.time() - t), flush=True)
sentence = "Ubuhinzi bw'ibigori busaba ubutaka bwiza."
for i in range(3):
    t = time.time()
    tts._synth(sentence)
    print(f"TTS call {i + 1}: {time.time() - t:.1f} s", flush=True)

if len(sys.argv) > 1 and sys.argv[1].lower() == "asr":
    import asr  # noqa: E402
    wav = Path("test") / "test.wav"
    if not wav.is_file():
        sys.exit("test/test.wav not found, so the speech test was skipped.")
    t = time.time()
    asr.load()
    print("ASR load: %.1f s" % (time.time() - t), flush=True)
    for i in range(2):
        t = time.time()
        heard = asr.transcribe(str(wav))
        print(f"ASR call {i + 1}: {time.time() - t:.1f} s | heard: {heard!r}", flush=True)
print("done")