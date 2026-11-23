"""Unit tests for the login rate limiter (Phase 6)."""
from app.services.login_ratelimit import LoginRateLimiter


class FakeClock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


def test_blocks_after_max_failures():
    rl = LoginRateLimiter(max_failures=3, window_seconds=60, clock=FakeClock())
    for _ in range(3):
        rl.record_failure("1.2.3.4")
    assert rl.is_blocked("1.2.3.4") is True


def test_not_blocked_below_limit():
    rl = LoginRateLimiter(max_failures=3, window_seconds=60, clock=FakeClock())
    rl.record_failure("1.2.3.4")
    rl.record_failure("1.2.3.4")
    assert rl.is_blocked("1.2.3.4") is False


def test_other_ip_is_not_affected():
    rl = LoginRateLimiter(max_failures=2, window_seconds=60, clock=FakeClock())
    rl.record_failure("1.1.1.1")
    rl.record_failure("1.1.1.1")
    assert rl.is_blocked("1.1.1.1") is True
    assert rl.is_blocked("9.9.9.9") is False


def test_block_lifts_after_window():
    clock = FakeClock()
    rl = LoginRateLimiter(max_failures=2, window_seconds=60, clock=clock)
    rl.record_failure("a")
    rl.record_failure("a")
    assert rl.is_blocked("a") is True
    clock.t = 61
    assert rl.is_blocked("a") is False


def test_successful_login_reset_clears_counter():
    rl = LoginRateLimiter(max_failures=2, window_seconds=60, clock=FakeClock())
    rl.record_failure("a")
    rl.record_failure("a")
    rl.reset("a")
    assert rl.is_blocked("a") is False


def test_unknown_ip_is_not_blocked():
    rl = LoginRateLimiter(clock=FakeClock())
    assert rl.is_blocked("never-seen") is False
