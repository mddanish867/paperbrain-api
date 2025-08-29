import json
import hashlib
from typing import Optional, List, Dict, Any
from datetime import timedelta, datetime
from app.services.redis import redis_client, is_redis_available
from app.utils.logger import logger

class CacheService:
    def __init__(self, default_ttl: int = 3600):
        self.default_ttl = default_ttl
        self.redis_available = is_redis_available()
        
        if not self.redis_available:
            logger.warning("⚠️  Redis not available - using in-memory fallback (not persistent)")
            self.memory_cache = {}
    
    def _ensure_redis(self) -> bool:
        """Check if Redis is available and try to reconnect if needed"""
        if self.redis_available:
            return True
        
        # Try to reconnect
        try:
            global redis_client
            from app.services.redis import get_redis_client
            redis_client = get_redis_client()
            self.redis_available = True
            logger.info("Redis reconnected successfully")
            return True
        except Exception:
            return False
    
    def _memory_get(self, key: str) -> Optional[Any]:
        """Get value from memory cache with expiration support"""
        if key not in self.memory_cache:
            return None
        
        value, expiration = self.memory_cache[key]
        if expiration and datetime.now() > expiration:
            del self.memory_cache[key]
            return None
        
        return value
    
    def _memory_set(self, key: str, value: Any, ttl: Optional[int] = None):
        """Set value in memory cache with TTL"""
        expiration = None
        if ttl:
            expiration = datetime.now() + timedelta(seconds=ttl)
        self.memory_cache[key] = (value, expiration)
    
    def _memory_delete(self, key: str):
        """Delete value from memory cache"""
        if key in self.memory_cache:
            del self.memory_cache[key]
    
    # -------- Query result cache --------
    def get_cache_key(self, query: str) -> str:
        """Generate a cache key for a query"""
        return f"paperbrain:query:{hashlib.md5(query.encode()).hexdigest()}"
    
    def get_cached_response(self, query: str) -> Optional[dict]:
        """Get cached response for a query"""
        try:
            cache_key = self.get_cache_key(query)
            
            if self._ensure_redis():
                cached = redis_client.get(cache_key)
                if cached:
                    return json.loads(cached)
            else:
                # Fallback to memory cache
                return self._memory_get(cache_key)
                
        except Exception as e:
            logger.error(f"Error getting cached response: {e}")
        return None
    
    def cache_response(self, query: str, response: dict, ttl: Optional[int] = None):
        """Cache a response for a query"""
        try:
            cache_key = self.get_cache_key(query)
            ttl = ttl or self.default_ttl
            
            if self._ensure_redis():
                redis_client.setex(cache_key, timedelta(seconds=ttl), json.dumps(response))
            else:
                # Fallback to memory cache
                self._memory_set(cache_key, response, ttl)
                
        except Exception as e:
            logger.error(f"Error caching response: {e}")
    
    def invalidate_cache(self, query: str):
        """Invalidate cache for a specific query"""
        try:
            cache_key = self.get_cache_key(query)
            
            if self._ensure_redis():
                redis_client.delete(cache_key)
            else:
                self._memory_delete(cache_key)
                
        except Exception as e:
            logger.error(f"Error invalidating cache: {e}")
    
    # -------- Conversation history --------
    def _convo_key(self, session_id: str) -> str:
        """Generate a conversation key"""
        return f"paperbrain:convo:{session_id}"
    
    def append_conversation(self, session_id: str, record: Dict, max_len: int = 10, ttl: int = 86400):
        """Append a message to conversation history"""
        try:
            key = self._convo_key(session_id)
            
            if self._ensure_redis():
                redis_client.rpush(key, json.dumps(record))
                
                # Trim list to last max_len entries
                length = redis_client.llen(key)
                if length > max_len:
                    redis_client.ltrim(key, length - max_len, -1)
                
                # Set expiration
                redis_client.expire(key, ttl)
            else:
                # Memory fallback for conversation history
                if key not in self.memory_cache:
                    self.memory_cache[key] = ([], datetime.now() + timedelta(seconds=ttl))
                
                messages, expiration = self.memory_cache[key]
                messages.append(record)
                
                # Trim to max length
                if len(messages) > max_len:
                    messages = messages[-max_len:]
                
                self.memory_cache[key] = (messages, expiration)
                
        except Exception as e:
            logger.error(f"Error appending to conversation: {e}")
    
    def get_conversation(self, session_id: str) -> List[Dict]:
        """Get entire conversation history"""
        try:
            key = self._convo_key(session_id)
            
            if self._ensure_redis():
                raw = redis_client.lrange(key, 0, -1) or []
                return [json.loads(x) for x in raw]
            else:
                # Memory fallback
                if key in self.memory_cache:
                    messages, expiration = self.memory_cache[key]
                    if expiration and datetime.now() > expiration:
                        del self.memory_cache[key]
                        return []
                    return messages
                
        except Exception as e:
            logger.error(f"Error getting conversation: {e}")
        return []
    
    def clear_conversation(self, session_id: str):
        """Clear conversation history"""
        try:
            key = self._convo_key(session_id)
            
            if self._ensure_redis():
                redis_client.delete(key)
            else:
                self._memory_delete(key)
                
        except Exception as e:
            logger.error(f"Error clearing conversation: {e}")
    
    # -------- Rate limiting --------
    def check_rate_limit(self, key: str, max_requests: int, window_seconds: int) -> bool:
        """Check if rate limit is exceeded"""
        try:
            full_key = f"paperbrain:rate:{key}"
            
            if self._ensure_redis():
                # Use Redis for rate limiting
                current = redis_client.get(full_key)
                count = int(current) if current else 0
                
                if count >= max_requests:
                    return False
                
                # Use pipeline for atomic operations
                pipe = redis_client.pipeline()
                pipe.incr(full_key)
                pipe.expire(full_key, window_seconds)
                pipe.execute()
                
                return True
            else:
                # Memory-based rate limiting
                current_time = datetime.now().timestamp()
                window_start = current_time - window_seconds
                
                if full_key not in self.memory_cache:
                    self.memory_cache[full_key] = ([current_time], current_time + window_seconds)
                    return True
                
                requests, expiration = self.memory_cache[full_key]
                
                # Clean up old requests
                requests = [req for req in requests if req > window_start]
                
                if len(requests) >= max_requests:
                    return False
                
                requests.append(current_time)
                self.memory_cache[full_key] = (requests, expiration)
                return True
                
        except Exception as e:
            logger.error(f"Error checking rate limit: {e}")
            return True  # Fail open
    
    # -------- User sessions --------
    def store_user_session(self, user_id: str, session_data: Dict, ttl: int = 86400):
        """Store user session data"""
        try:
            key = f"paperbrain:session:{user_id}"
            
            if self._ensure_redis():
                redis_client.setex(key, timedelta(seconds=ttl), json.dumps(session_data))
            else:
                self._memory_set(key, session_data, ttl)
                
        except Exception as e:
            logger.error(f"Error storing user session: {e}")
    
    def get_user_session(self, user_id: str) -> Optional[Dict]:
        """Get user session data"""
        try:
            key = f"paperbrain:session:{user_id}"
            
            if self._ensure_redis():
                data = redis_client.get(key)
                if data:
                    return json.loads(data)
            else:
                return self._memory_get(key)
                
        except Exception as e:
            logger.error(f"Error getting user session: {e}")
        return None
    
    def delete_user_session(self, user_id: str):
        """Delete user session data"""
        try:
            key = f"paperbrain:session:{user_id}"
            
            if self._ensure_redis():
                redis_client.delete(key)
            else:
                self._memory_delete(key)
                
        except Exception as e:
            logger.error(f"Error deleting user session: {e}")
    
    # -------- Health check --------
    def health_check(self) -> Dict:
        """Check cache service health"""
        redis_status = self._ensure_redis()
        return {
            "redis_available": redis_status,
            "memory_cache_size": len(self.memory_cache) if not redis_status else 0,
            "status": "healthy" if redis_status or self.memory_cache else "degraded"
        }

# Create singleton instance
cache_service = CacheService()