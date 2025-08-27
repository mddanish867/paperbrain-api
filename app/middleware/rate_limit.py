from app.services.redis_client import redis


class RateLimiter:
    def __init__(self, limit: int = 5, window: int = 60):
        self.limit = limit
        self.window = window

    def check_rate_limit(self, key: str):
        if redis is None:
            raise RuntimeError("Redis is not available. Did you set your UPSTASH env vars?")

        count = redis.incr(key)
        if count == 1:
            redis.expire(key, self.window)

        if count > self.limit:
            raise Exception("Too many requests. Please try again later.")
