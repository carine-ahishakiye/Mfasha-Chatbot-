#!/usr/bin/env python3
"""Performance and resource report for the demo video (rubric 2E) and docs/PERFORMANCE.md.

    python scripts/benchmark.py --runs 200 --threads 8 --out benchmark.json

Reports per-stage latency percentiles, throughput under concurrent load and peak memory, together
with the machine description, so results from a low-end laptop and a high-end one can be compared.
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import statistics
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mfasha.config import Settings  # noqa: E402
from mfasha.factory import build_pipeline  # noqa: E402

QUESTIONS = ["Ni gute nahinga ibigori?", "Inka zikenera iki?", "Nabona nte nkunganire ku ifumbire?",
             "Ibibabi by'ibishyimbo byahinduye ibara", "Ni nde watwaye igikombe cy'isi?"]


def percentile(values: list[float], q: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(round(q * (len(ordered) - 1))))]


def peak_memory_mb() -> float | None:
    try:
        import resource
        rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        return round(rss / (1024 * 1024 if sys.platform == "darwin" else 1024), 1)
    except ImportError:                       # Windows has no `resource` module
        return None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=int, default=200)
    parser.add_argument("--threads", type=int, default=8)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()

    started = time.perf_counter()
    pipeline, kb = build_pipeline(Settings.from_env())
    startup_s = time.perf_counter() - started

    totals, stages = [], {}
    for i in range(args.runs):
        result = pipeline.ask_text(QUESTIONS[i % len(QUESTIONS)])
        totals.append(result.latency_ms)
        for name, ms in result.stage_ms.items():
            stages.setdefault(name, []).append(ms)

    t0 = time.perf_counter()
    with ThreadPoolExecutor(args.threads) as pool:                     # stress: concurrent requests
        list(pool.map(lambda i: pipeline.ask_text(QUESTIONS[i % len(QUESTIONS)]), range(args.runs * 5)))
    throughput = args.runs * 5 / (time.perf_counter() - t0)

    report = {
        "machine": {"os": platform.platform(), "python": platform.python_version(),
                    "cpu_count": os.cpu_count(), "processor": platform.processor()},
        "components": pipeline.describe(), "passages": len(kb), "startup_s": round(startup_s, 2),
        "latency_ms": {"p50": round(statistics.median(totals), 2), "p95": round(percentile(totals, .95), 2),
                       "p99": round(percentile(totals, .99), 2), "max": round(max(totals), 2)},
        "stage_p50_ms": {k: round(statistics.median(v), 3) for k, v in stages.items()},
        "throughput_req_per_s": round(throughput, 1), "threads": args.threads,
        "peak_memory_mb": peak_memory_mb(),
    }
    print(json.dumps(report, indent=2))
    if args.out:
        args.out.write_text(json.dumps(report, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
