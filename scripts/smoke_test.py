
import argparse
import pickle
import sys
import time
import traceback
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from mfasha import config                                   # noqa: E402
from mfasha.text_utils import norm_key                      # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--skip", nargs="*", default=[])
args = ap.parse_args()
state, report = {}, []


def stage(name):
    def wrap(fn):
        if name in args.skip:
            report.append((name, "SKIPPED", ""))
            return fn
        print(f"\n--- {name} ---")
        t0 = time.time()
        try:
            note = fn() or ""
            report.append((name, "PASS", f"{note} ({time.time() - t0:.0f}s)"))
        except Exception as e:
            traceback.print_exc()
            report.append((name, "FAIL", f"{type(e).__name__}: {str(e)[:150]}"))
        return fn
    return wrap


@stage("assets")
def _():
    from mfasha.assets import ensure_assets
    ensure_assets()
    sizes = {p.name: round(p.stat().st_size / 1e6, 1) for p in config.REQUIRED_ASSETS if p.is_file()}
    return f"all files present {sizes}"


@stage("retrieval")
def _():
    from mfasha.retriever import Retriever
    r = Retriever.load()
    state["retriever"] = r
    cases = {"Intama zororoka gute?": "intama", "Umusaruro w'inkwavu uba uhagaze gute?": "inkwavu",
             "Umuhinzi abona bwishingizi bw'ibihingwa ate?": "shingizi"}
    for q, word in cases.items():
        top = r.search(q)[0]
        print(f"{q}\n   -> {top.text[:90]}  (score {top.score:.2f})")
        assert word in top.text.lower(), f"top passage for '{q}' does not mention '{word}'"
    return f"{len(r.passages)} passages, 3 of 3 questions found the right topic"


@stage("tts")
def _():
    from mfasha.tts import Speaker
    import scipy.io.wavfile as wf
    sp = Speaker()
    state["speaker"] = sp
    wav, spoken = sp.speak("Intama ihaka iminsi 149-152, amezi 5.")
    print("spoken text:", spoken)
    out = config.ROOT / "results" / "smoke_voice.wav"
    out.parent.mkdir(exist_ok=True)
    wf.write(out, sp.sr, wav)
    assert len(wav) > sp.sr, "audio is shorter than a second"
    return f"{len(wav) / sp.sr:.1f} s of audio saved to {out.name}. Open it and listen"


@stage("asr")
def _():
    import jiwer
    from mfasha.asr import Transcriber
    t = Transcriber()
    state["asr"] = t
    pkl = config.ROOT / "data" / "asr_test_male2.pkl"
    assert pkl.exists(), "data/asr_test_male2.pkl not found"
    clips = pickle.load(open(pkl, "rb"))[:20]
    refs, hyps = [], []
    for c in clips:
        hyps.append(norm_key(t.transcribe(np.asarray(c["audio"], dtype=np.float32))))
        refs.append(norm_key(c["text"]))
    for r_, h_ in list(zip(refs, hyps))[:3]:
        print("ref :", r_, "\nheard:", h_)
    wer = jiwer.wer(refs, hyps)
    assert wer < 0.6, f"WER {wer:.2f} is far above the 0.28 from your notebook, the adapter may not have loaded properly"
    return f"WER {wer:.2f} on 20 held-out clips (notebook: 0.28 on 200)"


@stage("end2end")
def _():
    from mfasha.pipeline import Mfasha
    assert "retriever" in state, "retrieval stage must pass first"
    bot = Mfasha(state["retriever"], state.get("asr"))
    for q in ["Intama zororoka gute?", "Ni nde watwaye igikombe cy'isi cya 2022?"]:
        res = bot.ask(text=q)
        print(f"{q}\n   status={res.status} | {res.answer}")
    ok = bot.ask(text="Intama zororoka gute?")
    off = bot.ask(text="Ni nde watwaye igikombe cy'isi cya 2022?")
    assert ok.status == "answered", f"farming question gave status {ok.status}"
    assert ok.answer == ok.hits[0].text, "the answer is not the stored passage"
    if bot.threshold:
        assert off.status == "referred", f"off-topic question gave status {off.status}"
        return "farming question answered, off-topic question referred"
    return "farming question answered (no referral threshold set, so off-topic questions are never referred)"


print("\nSUMMARY")
for name, status, note in report:
    print(f"{status:8s} {name:10s} {note}")
sys.exit(1 if any(s == "FAIL" for _, s, _ in report) else 0)
