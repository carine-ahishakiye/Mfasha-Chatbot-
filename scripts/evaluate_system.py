
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mfasha import config, evaluation as ev          # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--part", choices=["retrieval", "calibration", "answers", "speech", "all"], default="all")
ap.add_argument("--n-farming", type=int, default=80)
ap.add_argument("--n-speech", type=int, default=40)
ap.add_argument("--cap", type=int, default=0)
ap.add_argument("--seed", type=int, default=42)
ap.add_argument("--fast-asr", action="store_true")
ap.add_argument("--list-questions", type=int, default=0)
ap.add_argument("--off-topic", default=str(config.ROOT / "eval" / "off_topic_rw.txt"))
args = ap.parse_args()

if args.list_questions:
    ev.list_questions(args.list_questions, args.seed)
    sys.exit(0)

from mfasha.assets import ensure_assets               # noqa: E402
from mfasha.retriever import Retriever                # noqa: E402

ensure_assets()
report = ev.Report(config.ROOT / "results" / "evaluation_report.md")
report.add("# Evaluation report", "")
e = ev.Evaluator(Retriever.load(), report, cap=args.cap, seed=args.seed)
off_topic = ev.read_lines(args.off_topic)
parts = ["retrieval", "calibration", "answers", "speech"] if args.part == "all" else [args.part]

for part in parts:
    print(f"\n=== {part} ===")
    if part == "retrieval":
        e.part_retrieval()
    elif part == "calibration":
        e.part_calibration(off_topic)
    elif part == "answers":
        from mfasha.llm import ask_llm
        e.part_answers(ask_llm, off_topic, n_farming=args.n_farming)
    elif part == "speech":
        from mfasha.asr import Transcriber
        asr = Transcriber()
        if args.fast_asr:
            import torch
            asr.model = torch.quantization.quantize_dynamic(asr.model, {torch.nn.Linear}, dtype=torch.qint8)
            asr.quantized = True
        e.part_speech(asr, n=args.n_speech)
    report.save()           # saved after every part, so nothing is lost if a later part fails
print("\nDone. Open results/evaluation_report.md")