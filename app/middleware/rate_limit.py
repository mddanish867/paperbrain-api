from fastapi import HTTPException
from app.services.redis_client import redis

class RateLimiter:
    """
    Fixed-window rate limiter using Upstash Redis.
    Default: 100 requests per minute per IP.
    """
    def __init__(self, limit: int = 100, window_sec: int = 60):
        self.limit = limit
        self.window = window_sec

    def check_rate_limit(self, client_ip: str):
        key = f"rl:{client_ip}"
        # INCR returns the new value; set TTL on first hit
        count = redis.incr(key)
        if count == 1:
            redis.expire(key, self.window)
        if count > self.limit:
            raise HTTPException(status_code=429, detail="Rate limit exceeded")
