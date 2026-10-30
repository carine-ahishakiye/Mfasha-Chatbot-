from mfasha.ratelimit import RateLimiter


def test_blocks_after_the_limit_and_frees_after_the_window():
    now = [0.0]
    rl = RateLimiter(limit=2, window=60, clock=lambda: now[0])
    assert rl.allow("a") and rl.allow("a")
    assert not rl.allow("a")
    assert rl.allow("b")                   # another visitor is not affected
    now[0] = 61.0
    assert rl.allow("a")                   # the old requests have left the window
