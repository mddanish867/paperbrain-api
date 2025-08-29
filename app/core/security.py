from datetime import datetime, timedelta
from typing import Optional
from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import HTTPException, status, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from app.core.config import settings
from app.services.redis import redis_client

security = HTTPBearer()
pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_ctx.verify(plain_password, hashed_password)

def get_password_hash(password: str) -> str:
    return pwd_ctx.hash(password)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire, "type": "access"})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)

def create_refresh_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode.update({"exp": expire, "type": "refresh"})
    token = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    
    # Store token reference in Redis
    sub = data.get("sub")
    if sub:
        redis_client.setex(f"refresh:{sub}:{token[-16:]}", timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS), "1")
    return token

def decode_token(token: str) -> dict:
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        return payload
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> dict:
    token = credentials.credentials
    payload = decode_token(token)
    if payload.get("type") != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return payload

def generate_otp(email: str) -> str:
    import secrets
    code = f"{secrets.randbelow(900000) + 100000}"
    redis_client.setex(f"otp:{email}", timedelta(minutes=5), code)
    return code

def verify_otp(email: str, otp: str) -> bool:
    stored_otp = redis_client.get(f"otp:{email}")
    if stored_otp and stored_otp.decode("utf-8") == otp:
        redis_client.delete(f"otp:{email}")
        return True
    return False

def generate_reset_token(email: str) -> str:
    import secrets
    token = secrets.token_urlsafe(32)
    # Store hashed token for security
    token_hash = get_password_hash(token)
    redis_client.setex(f"reset:{email}", timedelta(minutes=15), token_hash)
    return token

def verify_reset_token(email: str, token: str) -> bool:
    stored_token_hash = redis_client.get(f"reset:{email}")
    if stored_token_hash and verify_password(token, stored_token_hash.decode("utf-8")):
        redis_client.delete(f"reset:{email}")
        return True
    return False