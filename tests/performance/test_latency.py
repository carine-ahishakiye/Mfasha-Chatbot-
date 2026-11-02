"""Latency budget (proposal section 3.4.2 and notebook CFG.max_response_s = 5 s)."""
import statistics
import time

import pytest

pytestmark = pytest.mark.performance


def test_text_pipeline_p95_is_well_below_the_five_second_budget(pipeline):
    questions = ["Ni gute nahinga ibigori?", "Inka zikenera iki?", "Nagurisha nte umusaruro?"] * 30
    timings = []
    for q in questions:
        start = time.perf_counter()
        pipeline.ask_text(q)
        timings.append((time.perf_counter() - start) * 1000)
    timings.sort()
    p50, p95 = statistics.median(timings), timings[int(len(timings) * 0.95) - 1]
    print(f"\nlight pipeline: p50 {p50:.1f} ms, p95 {p95:.1f} ms over {len(timings)} questions")
    assert p95 < 250
