import json
import hashlib
from typing import Optional, List, Dict
from app.services.redis_client import redis

class CacheService:
    # -------- Query result cache --------
    def get_cache_key(self, query: str) -> str:
        return f"query:{hashlib.md5(query.encode()).hexdigest()}"

    def get_cached_response(self, query: str) -> Optional[dict]:
        cache_key = self.get_cache_key(query)
        cached = redis.get(cache_key)
        return json.loads(cached) if cached else None

    def cache_response(self, query: str, response: dict, ttl: int = 3600):
        cache_key = self.get_cache_key(query)
        redis.set(cache_key, json.dumps(response), ex=ttl)

    # -------- Conversation history --------
    def _convo_key(self, session_id: str) -> str:
        return f"convo:{session_id}"

    def append_conversation(self, session_id: str, record: Dict, max_len: int = 10, ttl: int = 60 * 60 * 24):
        key = self._convo_key(session_id)
        redis.rpush(key, json.dumps(record))
        # Trim list to last max_len entries
        # Upstash doesn't support LTRIM negative indices; use explicit indices
        length = redis.llen(key) or 0
        if length > max_len:
            start = max(0, length - max_len)
            # emulate trim: fetch last max_len and replace list
            last = redis.lrange(key, start, length - 1) or []
            redis.delete(key)
            for item in last:
                redis.rpush(key, item)
        redis.expire(key, ttl)

    def get_conversation(self, session_id: str) -> List[Dict]:
        key = self._convo_key(session_id)
        raw = redis.lrange(key, 0, -1) or []
        return [json.loads(x) for x in raw]

    def clear_conversation(self, session_id: str):
        key = self._convo_key(session_id)
        redis.delete(key)
