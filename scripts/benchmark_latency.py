"""Measure MFASHA response time per pipeline stage and end to end."""

import argparse
import csv
import json
import os
import platform
import statistics
import sys
import time
from pathlib import Path

# the device has to be chosen before torch is imported
_pre = argparse.ArgumentParser(add_help=False)
_pre.add_argument("--device", choices=["cpu", "cuda"], default=None)
_known, _ = _pre.parse_known_args()
if _known.device == "cpu":
    os.environ["CUDA_VISIBLE_DEVICES"] = ""          # hides the GPU, so every model runs on the CPU

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import numpy as np                                    # noqa: E402

from mfasha import config                             # noqa: E402
from mfasha.audio import decode_audio                 # noqa: E402
from mfasha.text_utils import clean_text              # noqa: E402
from mfasha.voice import spoken_part                  # noqa: E402


def timed(fn, *args, **kwargs):
    t0 = time.perf_counter()
    out = fn(*args, **kwargs)
    return out, (time.perf_counter() - t0) * 1000     # milliseconds


def summary(values):
    v = sorted(values)
    if not v:
        return dict(n=0, mean=float("nan"), p50=float("nan"), p95=float("nan"), max=float("nan"))
    p95 = v[min(len(v) - 1, int(round(0.95 * (len(v) - 1))))]
    return dict(n=len(v), mean=statistics.fmean(v), p50=statistics.median(v), p95=p95, max=v[-1])


def load_questions(n):
    """Typed questions taken from the cleaned query file, spread evenly across it."""
    path = ROOT / "data" / "clean" / "queries.jsonl"
    rows = [json.loads(l)["text"] for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
    step = max(1, len(rows) // n)
    return rows[::step][:n]


def load_audio(n):
    """Voice clips from results/voice_test (the recordings already in the repository)."""
    files = sorted((ROOT / "results" / "voice_test").glob("*.wav"))[:n]
    return [(f.name, decode_audio(f.read_bytes())) for f in files]


def hardware_info():
    info = {"os": f"{platform.system()} {platform.release()}", "python": platform.python_version(),
            "cpu": platform.processor() or platform.machine(), "machine": platform.node()}
    try:
        import psutil
        info["cpu_cores"] = psutil.cpu_count(logical=True)
        info["ram_gb"] = round(psutil.virtual_memory().total / 1e9, 1)
    except ImportError:
        pass
    import torch
    info["torch"] = torch.__version__
    info["cuda_available"] = torch.cuda.is_available()
    if torch.cuda.is_available():
        info["gpu"] = torch.cuda.get_device_name(0)
    return info


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--device", choices=["cpu", "cuda"], default=None, help="cpu hides the GPU")
    ap.add_argument("--n-text", type=int, default=50)
    ap.add_argument("--n-voice", type=int, default=10)
    ap.add_argument("--warmup", type=int, default=3, help="runs thrown away before timing")
    ap.add_argument("--label", default=None)
    args = ap.parse_args()

    import torch
    device = "cuda" if torch.cuda.is_available() else "cpu"
    label = args.label or f"{device}_{platform.node()}".replace(" ", "_")

    # ---- cold start: how long the models take to load
    from mfasha.pipeline import Mfasha
    from mfasha.tts import Speaker
    bot, load_bot_ms = timed(Mfasha.load)
    speaker, load_tts_ms = timed(Speaker)
    print(f"models loaded on {device}: app {load_bot_ms/1000:.1f}s, speaker {load_tts_ms/1000:.1f}s")

    questions = load_questions(args.n_text)
    clips = load_audio(args.n_voice)

    # ---- warm-up (the first call is always slower: lazy initialisation, caches)
    for q in questions[:args.warmup]:
        bot.ask(text=q)
    if clips:
        bot.transcriber.transcribe(clips[0][1])
    speaker.speak("Muraho.")

    times = {k: [] for k in ["preprocess", "retrieval", "asr", "tts", "e2e_text", "e2e_text_with_tts", "e2e_voice_with_tts"]}
    outcomes = {"answered": 0, "referred": 0, "empty": 0}

    for q in questions:
        _, t = timed(clean_text, q)
        times["preprocess"].append(t)
        _, t = timed(bot.retriever.search, clean_text(q))
        times["retrieval"].append(t)
        res, t = timed(bot.ask, text=q)
        times["e2e_text"].append(t)
        outcomes[res.status] += 1
        if res.answer:
            part, _cut = spoken_part(res.answer)
            _, t_tts = timed(speaker.speak, part)
            times["tts"].append(t_tts)
            times["e2e_text_with_tts"].append(t + t_tts)

    for name, audio in clips:
        _, t_asr = timed(bot.transcriber.transcribe, audio)
        times["asr"].append(t_asr)
        res, t = timed(bot.ask, audio=audio)
        t_tts = 0.0
        if res.answer:
            part, _cut = spoken_part(res.answer)
            _, t_tts = timed(speaker.speak, part)
        times["e2e_voice_with_tts"].append(t + t_tts)

    # ---- resource use
    resources = {}
    try:
        import psutil
        resources["process_ram_mb"] = round(psutil.Process().memory_info().rss / 1e6)
    except ImportError:
        pass
    if torch.cuda.is_available():
        resources["gpu_peak_mem_mb"] = round(torch.cuda.max_memory_allocated() / 1e6)

    rows = []
    names = {
        "preprocess": "3. Text preprocessing",
        "retrieval": "5. Retrieval and ranking",
        "asr": "2. Speech-to-text",
        "tts": "7. Text-to-speech",
        "e2e_text": "End to end, typed question (text answer)",
        "e2e_text_with_tts": "End to end, typed question + spoken answer",
        "e2e_voice_with_tts": "End to end, voice question + spoken answer",
    }
    for key, title in names.items():
        s = summary(times[key])
        rows.append([title, s["n"], round(s["mean"], 1), round(s["p50"], 1), round(s["p95"], 1), round(s["max"], 1)])

    out_dir = ROOT / "results"
    out_dir.mkdir(exist_ok=True)
    with open(out_dir / f"benchmark_{label}.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["stage", "n", "mean_ms", "median_ms", "p95_ms", "max_ms"])
        w.writerows(rows)

    info = hardware_info()
    md = [f"# Latency benchmark: {label}", "", "## Environment", ""]
    md += [f"- {k}: {v}" for k, v in info.items()]
    md += [f"- model load time: app {load_bot_ms/1000:.1f} s, speaker {load_tts_ms/1000:.1f} s",
           f"- typed questions: {len(questions)}, voice clips: {len(clips)}, warm-up runs discarded: {args.warmup}",
           f"- outcomes of typed questions: {outcomes}"]
    md += [f"- {k}: {v}" for k, v in resources.items()]
    md += ["", "## Response time (milliseconds)", "",
           "| Stage | n | mean | median | p95 | max |", "|---|---:|---:|---:|---:|---:|"]
    md += ["| " + " | ".join(str(x) for x in r) + " |" for r in rows]
    (out_dir / f"benchmark_{label}.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print("\n".join(md))


if __name__ == "__main__":
    main()