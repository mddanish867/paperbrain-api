import os
from upstash_redis import Redis

redis = Redis(
    url=os.getenv("UPSTASH_REDIS_REST_URL"),
    token=os.getenv("UPSTASH_REDIS_REST_TOKEN")
)




def get_redis_client():
    if not redis.url or not redis.token:
        raise RuntimeError(
            "❌ Redis is not configured properly. "
            "Please set UPSTASH_REDIS_REST_URL and UPSTASH_REDIS_REST_TOKEN in your .env file."
        )
    return Redis(
        url=os.getenv("UPSTASH_REDIS_REST_URL"),
    token=os.getenv("UPSTASH_REDIS_REST_TOKEN")
    )


# Create global redis instance
try:
    redis = get_redis_client()
except RuntimeError as e:
    print(e)
    redis = None
