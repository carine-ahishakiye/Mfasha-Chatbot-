"""
speech_to_search.py - does the chatbot still find the right passage when the question comes from speech?

Offline test: it does not listen to audio. It reads the words the speech model already produced
(data/asr_before_test.csv and data/asr_after_test.csv) and searches with them.

    python speech_to_search.py                 # run from the project folder
    python speech_to_search.py --root "C:\\Users\\PC\\Desktop\\Mfasha chatbot"
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import pandas as pd

MIN_CHARS = 25     # a sentence must be at least this long (letters only) to be matched to a passage
MAX_SOURCES = 3    # a sentence found in more than this many passages is too general: skip it


def find_root() -> Path:
    here = Path.cwd().resolve()
    candidates = [here, *here.parents, Path(__file__).resolve().parent, *Path(__file__).resolve().parents]
    return next((p for p in candidates if (p / "src").exists()), here)


def squash(t: str) -> str:
    """Keep only letters and digits, lower case. 'n' amazi' and 'n'amazi' become the same string."""
    return re.sub(r"\W+", "", (t or "").lower().replace("_", ""))


def build_index(passages: list) -> dict:
    return {str(p["pid"]): squash(p["text"]) for p in passages}


def sources(ref: str, index: dict) -> set:
    """Which passage(s) contain this sentence? Empty set if it is too short or too general."""
    r = squash(ref)
    if len(r) < MIN_CHARS:
        return set()
    hits = {pid for pid, t in index.items() if r in t}
    return hits if 0 < len(hits) <= MAX_SOURCES else set()


def main(argv=None):
    ap = argparse.ArgumentParser(description="Speech-to-search test (offline, uses saved ASR transcripts)")
    ap.add_argument("--root", help="project folder containing src/ (default: auto-detect)")
    ap.add_argument("--data-dir", help="default: <root>/data")
    ap.add_argument("--model-dir", help="default: <root>/models")
    ap.add_argument("--device", default="cpu", help="cpu (default) or cuda")
    ap.add_argument("--k", type=int, default=5, help="top-k used for Recall@k (default 5)")
    ap.add_argument("--examples", type=int, default=5, help="failure examples to print (default 5)")
    args = ap.parse_args(argv)

    ROOT = Path(args.root).resolve() if args.root else find_root()
    DATA = Path(args.data_dir).resolve() if args.data_dir else ROOT / "data"
    MODEL_DIR = Path(args.model_dir).resolve() if args.model_dir else ROOT / "models"

    sys.path.insert(0, str(ROOT / "src"))
    try:
        import chatbot as cb
    except ModuleNotFoundError as e:
        if e.name != "chatbot":
            raise
        sys.exit(f"chatbot.py not found. Expected it in {ROOT / 'src'} (use --root).")

    need = {
        "retriever model": MODEL_DIR / "model.safetensors",
        "chunks": DATA / "chunks.jsonl",
        "chunk embeddings": DATA / "chunk_emb_e5.npy",
        "passages": DATA / "passages.jsonl",
        "speech results before": DATA / "asr_before_test.csv",
        "speech results after": DATA / "asr_after_test.csv",
    }
    for k, v in need.items():
        print("OK      " if v.exists() else "MISSING ", k, "->", v)
    if not all(v.exists() for v in need.values()):
        sys.exit("Put the MISSING files in the folders shown above, then run again.")

    bot = cb.Chatbot(model_dir=MODEL_DIR, chunks_path=DATA / "chunks.jsonl",
                     emb_path=DATA / "chunk_emb_e5.npy", device=args.device)
    r = bot.ask("soya ihunikwa ahantu hameze gute ?")
    print("chatbot ready:", len(bot.chunks), "chunks | test question -> confidence %.2f, level %s"
          % (r["confidence"], r.get("tier", "?")))

    # ---- find the "right passage" for every test sentence ----
    with open(DATA / "passages.jsonl", encoding="utf-8") as f:
        passages = [json.loads(l) for l in f if l.strip()]
    index = build_index(passages)

    b = pd.read_csv(DATA / "asr_before_test.csv").fillna("")
    a = pd.read_csv(DATA / "asr_after_test.csv").fillna("")
    d = (b[["set", "id", "ref", "hyp"]].rename(columns={"hyp": "hyp_b"})
         .merge(a[["set", "id", "hyp"]].rename(columns={"hyp": "hyp_a"}), on=["set", "id"]))
    d["src"] = d.ref.apply(lambda s: sources(s, index))
    d = d[d.src.apply(len) > 0].reset_index(drop=True)
    print("\ntest clips whose sentence is found inside 1 to %d passages: %d of %d (%d different sentences)"
          % (MAX_SOURCES, len(d), len(a), d.ref.apply(squash).nunique()))
    if len(d) == 0:
        sys.exit("No usable clips, so there is nothing to score.")
    if len(d) < 40:
        print("WARNING: too few clips for a reliable number.")

    # ---- search with the three texts (cached: each query runs once) ----
    cache: dict = {}

    def top(q: str):
        if q not in cache:
            res, conf = bot.search(q, k=args.k) if q.strip() else ([], 0.0)
            cache[q] = ([x["pid"] for x in res], conf)
        return cache[q]

    def run(col: str) -> dict:
        h1 = hk = refused = 0
        for q, src in zip(d[col], d.src):
            pids, conf = top(q)
            h1 += bool(pids) and pids[0] in src
            hk += any(p in src for p in pids)
            refused += conf < bot.threshold
        n = len(d)
        return {"Recall@1": h1 / n, f"Recall@{args.k}": hk / n, "would refuse": refused / n}

    tab = pd.DataFrame({"perfect text": run("ref"),
                        "speech, before training": run("hyp_b"),
                        "speech, after training": run("hyp_a")}).T
    print()
    print(tab.round(3).to_string())
    out = DATA / "speech_to_search.csv"
    tab.round(4).to_csv(out)
    print("\nsaved:", out)

    print("\nexamples where perfect text finds the passage but the speech text does not:")
    shown = 0
    for row in d.itertuples():
        if shown >= args.examples:
            break
        ref_top, hyp_top = top(row.ref)[0], top(row.hyp_a)[0]
        if ref_top[:1] and ref_top[0] in row.src and not (hyp_top[:1] and hyp_top[0] in row.src):
            print("  REF:", row.ref, "\n  HYP:", row.hyp_a, "\n")
            shown += 1
    if shown == 0:
        print("  none")


if __name__ == "__main__":
    main()