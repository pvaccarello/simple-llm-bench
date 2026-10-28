import time


class TokenBucket:
    def __init__(self, capacity, rate, clock=time.monotonic):
        if capacity <= 0 or rate <= 0:
            raise ValueError("capacity and rate must be positive")
        self.capacity = capacity
        self.rate = rate
        self.clock = clock
        self.tokens = float(capacity)
        self.last = clock()

    def _refill(self):
        now = self.clock()
        elapsed = now - self.last
        if elapsed > 0:
            self.tokens = min(self.capacity, self.tokens + elapsed * self.rate)
        self.last = now

    def try_acquire(self, n=1):
        if n <= 0:
            raise ValueError("n must be positive")
        self._refill()
        if self.tokens >= n:
            self.tokens -= n
            return True
        return False

    def wait_time(self, n=1):
        if n > self.capacity:
            return float("inf")
        self._refill()
        missing = n - self.tokens
        return max(0.0, missing / self.rate)

    def available(self):
        self._refill()
        return self.tokens
