
import threading
import time
from collections import defaultdict, deque


class RateLimiter:
    """Per-visitor limit, so one visitor cannot overload the models on a public link."""

    def __init__(self, limit: int, window: float = 60.0, clock=time.time):
        self.limit, self.window, self._clock = limit, window, clock
        self._seen = defaultdict(deque)
        self._lock = threading.Lock()

    def allow(self, key: str) -> bool:
        now = self._clock()
        with self._lock:
            q = self._seen[key]
            while q and q[0] < now - self.window:
                q.popleft()
            if len(q) >= self.limit:
                return False
            q.append(now)
            return True
