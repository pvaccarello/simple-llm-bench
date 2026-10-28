import pytest_shim as t
from solution import TokenBucket


class Clock:
    def __init__(self):
        self.now = 500.0

    def __call__(self):
        return self.now


def test_starts_full_and_consumes():
    b = TokenBucket(5, 1, clock=Clock())
    assert all(b.try_acquire() for _ in range(5))
    assert not b.try_acquire()


def test_cap_after_idle():
    clk = Clock()
    b = TokenBucket(5, 1, clock=clk)
    clk.now += 10_000
    assert t.approx(b.available(), 5)
    assert sum(b.try_acquire() for _ in range(20)) == 5


def test_fractional_rate_refills():
    clk = Clock()
    b = TokenBucket(2, 0.5, clock=clk)
    b.try_acquire(2)
    clk.now += 1
    assert t.approx(b.available(), 0.5)
    clk.now += 1
    assert b.try_acquire()


def test_subsecond_refill():
    clk = Clock()
    b = TokenBucket(10, 4, clock=clk)
    b.try_acquire(10)
    clk.now += 0.25
    assert b.try_acquire()
    assert not b.try_acquire()


def test_rejected_does_not_consume():
    clk = Clock()
    b = TokenBucket(3, 1, clock=clk)
    assert not b.try_acquire(5)
    assert t.approx(b.available(), 3)
    b.try_acquire(2)
    assert not b.try_acquire(2)
    assert t.approx(b.available(), 1)


def test_invalid_n():
    b = TokenBucket(3, 1, clock=Clock())
    t.raises(ValueError, b.try_acquire, 0)
    t.raises(ValueError, b.try_acquire, -1)


def test_clock_backwards():
    clk = Clock()
    b = TokenBucket(4, 1, clock=clk)
    b.try_acquire(4)
    clk.now -= 1000
    assert t.approx(b.available(), 0)
    clk.now += 2
    assert t.approx(b.available(), 2)


def test_wait_time():
    clk = Clock()
    b = TokenBucket(4, 2, clock=clk)
    assert b.wait_time(1) == 0.0
    b.try_acquire(4)
    assert t.approx(b.wait_time(1), 0.5)
    assert t.approx(b.wait_time(4), 2.0)
    assert b.wait_time(5) == float("inf")
    assert t.approx(b.available(), 0)


def test_constructor_validation():
    t.raises(ValueError, TokenBucket, 0, 1)
    t.raises(ValueError, TokenBucket, 1, 0)
