import time
from fastapi import HTTPException, status, Request
from fastapi.security import HTTPBearer
from typing import Callable, Optional
from app.services.cache import cache_service
from app.utils.logger import logger

class RateLimiter:
    def __init__(self, max_requests: int = 5, window_seconds: int = 600):
        """
        :param max_requests: How many requests allowed in the window
        :param window_seconds: Time window in seconds
        """
        self.max_requests = max_requests
        self.window = window_seconds

    def check_rate_limit(self, key: str) -> bool:
        """
        Returns True if allowed, False if rate limit exceeded.
        Uses the cache service which handles RedisLab or fallback.
        """
        return cache_service.check_rate_limit(key, self.max_requests, self.window)

    async def __call__(self, request: Request):
        """FastAPI dependency that checks rate limit"""
        # Get client IP
        client_ip = request.client.host if request.client else "unknown"
        
        # Get user identity if available
        user_identity = "anonymous"
        try:
            auth_header = request.headers.get("Authorization")
            if auth_header and auth_header.startswith("Bearer "):
                token = auth_header[7:]
                # Use part of the token for identity (not the whole token for security)
                user_identity = f"user:{token[-8:]}" if len(token) >= 8 else "user:unknown"
        except:
            pass
        
        # Create rate limit key with namespace for RedisLab
        endpoint = request.url.path
        rate_key = f"ratelimit:{endpoint}:{client_ip}:{user_identity}"
        
        if not self.check_rate_limit(rate_key):
            logger.warning(f"Rate limit exceeded for {rate_key}")
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Too many requests. Try again in {self.window} seconds.",
                headers={"Retry-After": str(self.window)}
            )

# Rate limiters for different endpoints
login_rate_limiter = RateLimiter(max_requests=5, window_seconds=600)
password_rate_limiter = RateLimiter(max_requests=3, window_seconds=900)
otp_rate_limiter = RateLimiter(max_requests=3, window_seconds=600)
api_rate_limiter = RateLimiter(max_requests=100, window_seconds=60)

# Dependency functions
def get_login_rate_limiter():
    return login_rate_limiter

def get_password_rate_limiter():
    return password_rate_limiter

def get_otp_rate_limiter():
    return otp_rate_limiter

def get_api_rate_limiter():
    return api_rate_limiter

# Middleware for global rate limiting
async def rate_limit_middleware(request: Request, call_next):
    """Global rate limiting middleware"""
    # Skip rate limiting for certain paths
    if request.url.path in ["/", "/health", "/docs", "/redoc", "/favicon.ico"]:
        return await call_next(request)
    
    # Apply general API rate limiting
    client_ip = request.client.host if request.client else "unknown"
    api_rate_key = f"ratelimit:global:{client_ip}"
    
    if not api_rate_limiter.check_rate_limit(api_rate_key):
        logger.warning(f"Global API rate limit exceeded for {client_ip}")
        from fastapi.responses import JSONResponse
        return JSONResponse(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            content={"detail": "Too many requests. Please try again later."},
            headers={"Retry-After": "60"}
        )
    
    return await call_next(request)