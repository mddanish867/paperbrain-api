import os
from redis import Redis, ConnectionPool
from redis.exceptions import ConnectionError, AuthenticationError
from app.core.config import settings
from app.utils.logger import logger

def get_redis_client():
    """
    Create and return a Redis client configured for RedisLab cloud
    RedisLab URLs are typically in format: redis://username:password@host:port
    """
    try:
        # Parse Redis URL for additional configuration
        redis_url = str(settings.REDIS_URL)
        
        # Create connection pool for better performance
        pool = ConnectionPool.from_url(
            redis_url,
            max_connections=20,
            socket_connect_timeout=5,
            socket_timeout=5,
            retry_on_timeout=True,
            health_check_interval=30
        )
        
        # Create Redis client
        client = Redis(connection_pool=pool, decode_responses=False)
        
        # Test connection
        client.ping()
        logger.info("RedisLab connection successful")
        
        return client
        
    except AuthenticationError:
        logger.error("❌ RedisLab authentication failed. Check credentials.")
        raise
    except ConnectionError:
        logger.error("❌ Cannot connect to RedisLab. Check URL and network.")
        raise
    except Exception as e:
        logger.error(f"❌ RedisLab connection error: {e}")
        raise

# Create singleton instance with connection handling
try:
    redis_client = get_redis_client()
except Exception:
    # Fallback to a dummy client that will fail gracefully
    logger.warning("⚠️  Using fallback Redis client (operations will fail)")
    redis_client = None

def is_redis_available():
    """Check if Redis is available"""
    if redis_client is None:
        return False
    try:
        return redis_client.ping()
    except:
        return False