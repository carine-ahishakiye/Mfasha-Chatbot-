
import json
import random
import time
from pathlib import Path

import numpy as np

from . import config
from .confidence import ConfidencePolicy
from .text_utils import clean_text, norm_key

DATA = config.ROOT / "data" / "clean"
SPLITS = ("train", "dev_seen", "test_seen", "dev_unseen", "test_unseen")


# ----------------------------------------------------------------------------- metrics
def bootstrap_ci(values, n_boot=2000, seed=0):
    """(mean, low, high) with a 95% bootstrap interval."""
    v = np.asarray(values, dtype=float)
    if len(v) == 0:
        return float("nan"), float("nan"), float("nan")
    rng = np.random.default_rng(seed)
    means = v[rng.integers(0, len(v), (n_boot, len(v)))].mean(axis=1)
    return float(v.mean()), float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))


def paired_diff_ci(a, b, **kw):
    """Mean of a - b per question, with a bootstrap interval. If the interval excludes 0 the gap is not luck."""
    return bootstrap_ci(np.asarray(a, dtype=float) - np.asarray(b, dtype=float), **kw)


def fmt(ci, pct=False):
    m, lo, hi = ci
    if np.isnan(m):
        return "n/a"
    return f"{100 * m:.1f}% [{100 * lo:.1f}, {100 * hi:.1f}]" if pct else f"{m:.3f} [{lo:.3f}, {hi:.3f}]"


def auroc(pos, neg):
    """Chance that a random positive scores higher than a random negative (ties count half)."""
    pos, neg = np.asarray(pos, dtype=float), np.asarray(neg, dtype=float)
    if len(pos) == 0 or len(neg) == 0:
        return float("nan")
    return float((pos[:, None] > neg[None, :]).mean() + 0.5 * (pos[:, None] == neg[None, :]).mean())


def choose_cutoff(margins, correct, target, min_n=30):
    """Lowest margin cutoff whose group (margin >= cutoff) is at least `target` accurate and has min_n items."""
    margins, correct = np.asarray(margins, dtype=float), np.asarray(correct, dtype=float)
    order = np.argsort(-margins)
    cum = np.cumsum(correct[order]) / np.arange(1, len(order) + 1)
    best = None
    for i in range(min_n - 1, len(cum)):
        if cum[i] >= target:
            best = i
    return None if best is None else float(margins[order][best])


def retrieval_scores(rows):
    """Per-question 0/1 and reciprocal-rank arrays from rows made by run_retrieval."""
    out = {f"R@{k}": [] for k in (1, 5, 10)}
    out["MRR@10"] = []
    for r in rows:
        pids = r["pids"]
        for k in (1, 5, 10):
            out[f"R@{k}"].append(int(r["gold"] in pids[:k]))
        out["MRR@10"].append(1.0 / (pids.index(r["gold"]) + 1) if r["gold"] in pids[:10] else 0.0)
    return {k: np.array(v) for k, v in out.items()}


# ----------------------------------------------------------------------------- data
def load_split(name, cap=0, seed=42):
    """[(qid, question text, gold passage id)] for one split."""
    import pandas as pd
    csv, qj = DATA / "splits" / f"{name}.csv", DATA / "queries.jsonl"
    if not csv.exists() or not qj.exists():
        raise FileNotFoundError(f"Need {csv} and {qj}. Copy data/clean/splits and queries.jsonl from your Drive.")
    df = pd.read_csv(csv, dtype=str)
    if not {"qid", "pos_pid"} <= set(df.columns):
        raise ValueError(f"{csv.name} has columns {list(df.columns)}, expected qid and pos_pid")
    qtext = {}
    for line in qj.read_text(encoding="utf-8").splitlines():
        if line.strip():
            r = json.loads(line)
            qtext[r["qid"]] = r["text"]
    items = [(r.qid, qtext[r.qid], r.pos_pid) for r in df.itertuples() if r.qid in qtext]
    if cap and len(items) > cap:
        items = random.Random(seed).sample(items, cap)
    return items


def run_retrieval(retr, items, k=10, label=""):
    rows = []
    for i, (qid, text, gold) in enumerate(items):
        hits = retr.search(clean_text(text), k=k)
        rows.append({"qid": qid, "gold": gold, "pids": [h.pid for h in hits], "top": hits[0].score,
                     "margin": hits[0].score - (hits[1].score if len(hits) > 1 else 0.0)})
        if label and (i + 1) % 200 == 0:
            print(f"  {label}: {i + 1}/{len(items)}")
    return rows


def read_lines(path):
    return [l.strip() for l in Path(path).read_text(encoding="utf-8").splitlines() if l.strip()]


class Report:
    def __init__(self, path):
        self.path, self.lines = Path(path), []

    def add(self, *lines):
        self.lines.extend(lines)

    def save(self):
        self.path.parent.mkdir(exist_ok=True)
        self.path.write_text("\n".join(self.lines) + "\n", encoding="utf-8")
        print("report saved to", self.path)


def table(header, rows):
    return ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)] + ["| " + " | ".join(map(str, r)) + " |" for r in rows]


# ----------------------------------------------------------------------------- state shared by the parts
class Evaluator:
    def __init__(self, retr, report, cap=0, seed=42):
        self.retr, self.report, self.cap, self.seed = retr, report, cap, seed
        self._rows, self._cal = {}, None
        self.passage_text = {p["pid"]: p["text"] for p in retr.passages}

    def rows(self, split):
        if split not in self._rows:
            print(f"retrieving for {split} ...")
            self._rows[split] = run_retrieval(self.retr, load_split(split, self.cap, self.seed), label=split)
        return self._rows[split]

    # --- retrieval
    def part_retrieval(self):
        out = ["## Retrieval (typed questions)", ""]
        body = []
        for split in ("test_seen", "test_unseen"):
            sc = retrieval_scores(self.rows(split))
            body.append([split, len(sc["R@1"])] + [fmt(bootstrap_ci(sc[m])) for m in ("R@1", "R@5", "R@10", "MRR@10")])
        out += table(["split", "questions", "R@1", "R@5", "R@10", "MRR@10"], body)
        out += ["", "Brackets are 95% bootstrap intervals.", ""]
        self.report.add(*out)

    # --- calibration
    def calibration(self):
        """Fit on DEV, never on test."""
        if self._cal is not None:
            return self._cal
        dev = self.rows("dev_unseen") + self.rows("dev_seen")
        margin = np.array([r["margin"] for r in dev])
        top = np.array([r["top"] for r in dev])
        correct = np.array([int(r["pids"][0] == r["gold"]) for r in dev])
        self._cal = {
            "high": choose_cutoff(margin, correct, 0.95), "medium": choose_cutoff(margin, correct, 0.85),
            "min_score": float(np.percentile(top[correct == 1] if correct.any() else top, 5)), "dev_n": len(dev), "dev_top1": float(correct.mean()),
        }
        return self._cal

    def tier(self, r, cal):
        # same rule as the web app (mfasha.confidence); here the cutoffs come from the development data
        return ConfidencePolicy(high_margin=cal["high"], medium_margin=cal["medium"]).classify(r["top"], r["margin"])

    def part_calibration(self, off_topic):
        cal = self.calibration()
        test = self.rows("test_unseen")
        out = ["## Calibration (fitted on the development splits)", ""]
        out += [f"Development questions used: {cal['dev_n']} (top-1 accuracy {cal['dev_top1']:.3f}).", ""]
        out += [f"- `TIER_HIGH_MARGIN` = {cal['high'] if cal['high'] is None else round(cal['high'], 4)} (groups of at least 95% accuracy)",
                f"- `TIER_MEDIUM_MARGIN` = {cal['medium'] if cal['medium'] is None else round(cal['medium'], 4)} (groups of at least 85% accuracy)",
                f"- `REFERRAL_THRESHOLD` = {cal['min_score']:.4f} (5th percentile of the top scores of correctly answered development questions, the same rule as the notebook)", ""]
        body = []
        for t in ("high", "medium", "low"):
            sel = [r for r in test if self.tier(r, cal) == t]
            acc = bootstrap_ci([int(r["pids"][0] == r["gold"]) for r in sel]) if sel else (float("nan"),) * 3
            body.append([t, len(sel), f"{100 * len(sel) / max(len(test), 1):.0f}%", fmt(acc, pct=True)])
        out += ["Top-1 accuracy per confidence level on test_unseen (cutoffs fitted on development data):", ""]
        out += table(["level", "questions", "share", "top-1 accuracy"], body)
        if off_topic:
            off = run_retrieval(self.retr, [(str(i), q, "") for i, q in enumerate(off_topic)])
            a_top = auroc([r["top"] for r in test], [r["top"] for r in off])
            a_mar = auroc([r["margin"] for r in test], [r["margin"] for r in off])
            refused = np.mean([r["top"] < cal["min_score"] for r in off])
            out += ["", f"Telling farming questions from off-topic ones ({len(test)} vs {len(off)} questions): "
                        f"AUROC of the best score {a_top:.3f}, of the margin {a_mar:.3f}. "
                        f"At the threshold above, {100 * refused:.0f}% of the off-topic questions are refused by score alone.", ""]
        self.report.add(*out)

    # --- answers
    def part_answers(self, off_topic, n_farming=80):
        """No language model: the answer is the top passage, or a referral when its score is below the threshold."""
        cal = self.calibration()
        thr = config.REFERRAL_THRESHOLD or cal["min_score"]
        questions = load_split("test_unseen", 0, self.seed)
        questions = random.Random(self.seed).sample(questions, min(n_farming, len(questions)))

        rows = []
        for qid, text, gold in questions:
            t0 = time.perf_counter()
            hits = self.retr.search(clean_text(text))
            referred = hits[0].score < thr
            rows.append({"qid": qid, "question": text, "gold": gold, "top_pid": hits[0].pid,
                         "top_score": hits[0].score, "referred": int(referred),
                         "right_passage": int(hits[0].pid == gold), "gold_in_top5": int(gold in [h.pid for h in hits]),
                         "latency_s": time.perf_counter() - t0})
        off = [self.retr.search(clean_text(q))[0].score for q in off_topic]

        answered = [r for r in rows if not r["referred"]]
        out = ["## Answer step: top passage with a referral threshold (no language model)", "",
               f"{len(rows)} questions from the unseen-passage test split and {len(off_topic)} off-topic questions. "
               f"Referral threshold {thr:.3f}. The answer shown is the stored passage, unchanged, so its text is always "
               "correct for the passage it comes from; what can go wrong is showing the wrong passage.", ""]
        body = [
            ["farming questions answered", f"{len(answered)} of {len(rows)}", fmt(bootstrap_ci([1 - r["referred"] for r in rows]), pct=True)],
            ["right passage among answered", f"{sum(r['right_passage'] for r in answered)} of {len(answered)}",
             fmt(bootstrap_ci([r["right_passage"] for r in answered]), pct=True)],
            ["farming questions wrongly referred", f"{len(rows) - len(answered)} of {len(rows)}",
             fmt(bootstrap_ci([r["referred"] for r in rows]), pct=True)],
            ["right passage in top 5", f"{sum(r['gold_in_top5'] for r in rows)} of {len(rows)}",
             fmt(bootstrap_ci([r["gold_in_top5"] for r in rows]), pct=True)],
        ]
        if off:
            body.append(["off-topic questions referred", f"{sum(s < thr for s in off)} of {len(off)}",
                         fmt(bootstrap_ci([int(s < thr) for s in off]), pct=True)])
        out += table(["measure", "count", "share [95% interval]"], body)
        lat = np.array([r["latency_s"] for r in rows])
        out += ["", f"Search time per question: median {np.median(lat) * 1000:.0f} ms, 95th percentile {np.percentile(lat, 95) * 1000:.0f} ms.", ""]
        self.report.add(*out)
        import pandas as pd
        path = config.ROOT / "results" / "referral_eval.csv"
        path.parent.mkdir(exist_ok=True)
        pd.DataFrame(rows).to_csv(path, index=False)
        print("per-question results saved to", path)

    # --- speech
    def gold_passages_for_sentence(self, sentence):
        key = norm_key(sentence)
        if len(key.split()) < 4:
            return set()
        return {p["pid"] for p in self.retr.passages if key in norm_key(p["text"])}

    def part_speech(self, transcriber, n=40, pkl=None, spoken_dir=None):
        import pickle
        import jiwer
        out = ["## Speech recognition and retrieval", ""]
        pkl = Path(pkl or config.ROOT / "data" / "asr_test_male2.pkl")
        if pkl.exists():
            clips = pickle.load(open(pkl, "rb"))
            step = max(1, len(clips) // n)
            clips = clips[::step][:n]
            refs, hyps, rows_ref, rows_asr, audio_s, used_s = [], [], [], [], 0.0, 0.0
            for c in clips:
                audio = np.asarray(c["audio"], dtype=np.float32)
                t0 = time.time()
                hyp = norm_key(transcriber.transcribe(audio))
                used_s += time.time() - t0
                audio_s += len(audio) / config.ASR_SR
                ref = norm_key(c["text"])
                refs.append(ref)
                hyps.append(hyp)
                gold = self.gold_passages_for_sentence(c["text"])
                if gold:
                    for q, store in ((ref, rows_ref), (hyp, rows_asr)):
                        hits = self.retr.search(q or "x", k=10)
                        store.append({"pids": [h.pid for h in hits], "gold": gold})
            wer = jiwer.wer(refs, hyps)
            out += [f"Held-out speaker, {len(clips)} sentences evenly spread over the test set. "
                    f"Word error rate {100 * wer:.1f}%. Speed: {used_s / max(audio_s, 1e-9):.2f} seconds of computing per second of audio "
                    f"({'int8' if getattr(transcriber, 'quantized', False) else 'standard'} model).", ""]
            if rows_ref:
                def hit(rows, k):
                    return np.array([int(bool(r["gold"] & set(r["pids"][:k]))) for r in rows])
                body = []
                for k in (1, 5, 10):
                    a, b = hit(rows_ref, k), hit(rows_asr, k)
                    body.append([f"R@{k}", fmt(bootstrap_ci(a)), fmt(bootstrap_ci(b)), fmt(paired_diff_ci(b, a))])
                out += [f"Sentence as query (gold = the passage that contains the sentence; {len(rows_ref)} of {len(clips)} sentences matched a passage):", ""]
                out += table(["metric", "reference text", "speech recognition output", "difference (speech minus text)"], body)
                out += ["", "These queries are sentences from the passages, not farmers' questions, so this shows how recognition "
                            "errors affect retrieval but is not the same as the spoken-question test below.", ""]
            else:
                out += ["No test sentence could be matched to a passage, so the sentence-as-query test was skipped.", ""]
        else:
            out += [f"{pkl} not found, sentence test skipped.", ""]

        spoken_dir = Path(spoken_dir or config.ROOT / "data" / "spoken_questions")
        wavs = sorted(spoken_dir.glob("*.wav")) if spoken_dir.exists() else []
        if wavs:
            known = {}
            for s in SPLITS:
                try:
                    for qid, text, gold in load_split(s):
                        known[qid] = (text, gold)
                except FileNotFoundError:
                    pass
            typed, spoken, errs, t_ref, t_hyp = [], [], [], [], []
            for w in wavs:
                if w.stem not in known:
                    continue
                text, gold = known[w.stem]
                hyp = transcriber.transcribe(load_wav_16k(w))
                t_ref.append(norm_key(text))
                t_hyp.append(norm_key(hyp))
                typed.append({"pids": [h.pid for h in self.retr.search(clean_text(text), k=10)], "gold": gold})
                spoken.append({"pids": [h.pid for h in self.retr.search(clean_text(hyp) or "x", k=10)], "gold": gold})
            if typed:
                a, b = retrieval_scores([{**r, "gold": r["gold"]} for r in typed]), retrieval_scores(spoken)
                body = [[m, fmt(bootstrap_ci(a[m])), fmt(bootstrap_ci(b[m])), fmt(paired_diff_ci(b[m], a[m]))] for m in ("R@1", "R@5", "R@10", "MRR@10")]
                out += [f"Spoken questions: {len(typed)} recordings of test questions, word error rate {100 * jiwer.wer(t_ref, t_hyp):.1f}%.", ""]
                out += table(["metric", "typed question", "spoken question", "difference (spoken minus typed)"], body) + [""]
        else:
            out += [f"No recordings in {spoken_dir}. Record test questions as <qid>.wav files (see --list-questions) "
                    "for the spoken-question test, which is the most convincing end-to-end result.", ""]
        self.report.add(*out)


def load_wav_16k(path):
    from math import gcd
    import soundfile as sf
    from scipy.signal import resample_poly
    y, sr = sf.read(str(path), dtype="float32")
    if y.ndim > 1:
        y = y.mean(axis=1)
    if sr != config.ASR_SR:
        g = gcd(int(sr), config.ASR_SR)
        y = resample_poly(y, config.ASR_SR // g, int(sr) // g).astype(np.float32)
    return y


def list_questions(n, seed=42):
    """Questions to read aloud and record as <qid>.wav."""
    import csv
    items = random.Random(seed).sample(load_split("test_unseen"), n)
    out = config.ROOT / "data" / "spoken_questions"
    out.mkdir(parents=True, exist_ok=True)
    with open(out / "to_read.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["qid", "question"])
        for qid, text, _ in items:
            w.writerow([qid, text])
    print(f"Wrote {out / 'to_read.csv'}. Read each question aloud and save it as {out}\\<qid>.wav")