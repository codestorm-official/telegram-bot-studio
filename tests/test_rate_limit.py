import unittest

from bot.panel.rate_limit import LoginRateLimiter


class LoginRateLimiterTests(unittest.TestCase):
    def test_blocks_after_limit_and_resets(self):
        limiter = LoginRateLimiter(max_attempts=3, window_seconds=60)
        for stamp in (1.0, 2.0, 3.0):
            limiter.record_failure("client", now=stamp)

        self.assertTrue(limiter.is_blocked("client", now=4.0))
        limiter.reset("client")
        self.assertFalse(limiter.is_blocked("client", now=4.0))

    def test_expired_attempts_do_not_block(self):
        limiter = LoginRateLimiter(max_attempts=2, window_seconds=10)
        limiter.record_failure("client", now=1.0)
        limiter.record_failure("client", now=2.0)

        self.assertFalse(limiter.is_blocked("client", now=20.0))


if __name__ == "__main__":
    unittest.main()
