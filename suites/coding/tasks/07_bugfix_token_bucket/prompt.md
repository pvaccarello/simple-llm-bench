The following module implements a token-bucket rate limiter used to throttle API clients. Users report that:

1. "After a long idle period, clients can suddenly burst far more requests than the bucket capacity."
2. "With a rate of 0.5 tokens/second, the bucket never refills at all."
3. "A request for more tokens than the capacity sometimes drains the bucket even though it is rejected."
4. "When the system clock is adjusted backwards, clients get blocked for a very long time."
5. "`wait_time` sometimes returns negative numbers."

Find and fix **all** bugs so the class matches its docstrings. Keep the public API (class name, method names, signatures) unchanged.

```python
import time


class TokenBucket:
    """Token bucket with `capacity` tokens, refilled continuously at `rate` tokens/second.

    The bucket starts full. `clock` is a zero-argument callable returning seconds.
    """

    def __init__(self, capacity, rate, clock=time.monotonic):
        if capacity <= 0 or rate <= 0:
            raise ValueError("capacity and rate must be positive")
        self.capacity = capacity
        self.rate = rate
        self.clock = clock
        self.tokens = capacity
        self.last = clock()

    def _refill(self):
        """Add the tokens accumulated since the last refill, never exceeding capacity.

        If the clock went backwards, no tokens are added and the reference time is reset
        to the current clock value.
        """
        now = self.clock()
        elapsed = now - self.last
        self.tokens += int(elapsed) * self.rate
        self.last = now

    def try_acquire(self, n=1):
        """Take `n` tokens if available and return True; otherwise take nothing and return False.

        `n` must be positive, otherwise ValueError.
        """
        self._refill()
        self.tokens -= n
        if self.tokens >= 0:
            return True
        return False

    def wait_time(self, n=1):
        """Seconds to wait until `n` tokens are available (0.0 if available now).

        Returns float('inf') if `n` exceeds capacity. Does not consume tokens.
        """
        self._refill()
        missing = n - self.tokens
        return missing / self.rate

    def available(self):
        """Current number of tokens (a float), after refilling."""
        self._refill()
        return self.tokens
```

Return the full corrected module.
