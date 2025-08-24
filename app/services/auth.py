from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt
from passlib.context import CryptContext
import os, secrets
from datetime import datetime, timedelta
from app.services.redis_client import redis

security = HTTPBearer()

# ---- JWT config
JWT_SECRET = os.getenv("JWT_SECRET_KEY", "change_me")
JWT_ALG = os.getenv("JWT_ALGORITHM", "HS256")
ACCESS_EXP_MIN = int(os.getenv("JWT_ACCESS_EXPIRES_MIN", "15"))
REFRESH_EXP_DAYS = int(os.getenv("JWT_REFRESH_EXPIRES_DAYS", "7"))

pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")

class AuthService:
    def __init__(self):
        self.secret_key = JWT_SECRET
        self.algorithm = JWT_ALG

    # ---- Password hashing
    def hash_password(self, plain: str) -> str:
        return pwd_ctx.hash(plain)

    def verify_password(self, plain: str, hashed: str) -> bool:
        return pwd_ctx.verify(plain, hashed)

    # ---- Tokens
    def create_access_token(self, data: dict) -> str:
        to_encode = data.copy()
        to_encode.update({"type": "access", "exp": datetime.utcnow() + timedelta(minutes=ACCESS_EXP_MIN)})
        return jwt.encode(to_encode, self.secret_key, algorithm=self.algorithm)

    def create_refresh_token(self, data: dict) -> str:
        to_encode = data.copy()
        to_encode.update({"type": "refresh", "exp": datetime.utcnow() + timedelta(days=REFRESH_EXP_DAYS)})
        token = jwt.encode(to_encode, self.secret_key, algorithm=self.algorithm)
        # Optional allowlist (store suffix)
        sub = data.get("sub", "unknown")
        redis.set(f"refresh:{sub}:{token[-16:]}", "1", ex=REFRESH_EXP_DAYS*24*3600)
        return token

    def create_tokens(self, sub: str):
        return (
            self.create_access_token({"sub": sub}),
            self.create_refresh_token({"sub": sub})
        )

    def decode_token(self, token: str) -> dict:
        return jwt.decode(token, self.secret_key, algorithms=[self.algorithm])

    # FastAPI dependency (validates Access token)
    def verify_token(self, credentials: HTTPAuthorizationCredentials = Depends(security)):
        try:
            data = self.decode_token(credentials.credentials)
            if data.get("type") != "access":
                raise ValueError("Not an access token")
            return data
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token"
            )

    # ---- Email verify / reset tokens / OTP stored in Upstash Redis
    def new_verify_email_token(self, email: str) -> str:
        token = secrets.token_urlsafe(24)
        redis.set(f"email_verify:{email}", token, ex=3600) # 1h
        return token

    def check_verify_email_token(self, email: str, token: str) -> bool:
        val = redis.get(f"email_verify:{email}")
        return bool(val and val == token)

    def new_reset_token(self, email: str) -> str:
        token = secrets.token_urlsafe(24)
        redis.set(f"reset:{email}", token, ex=900) # 15 min
        return token

    def check_reset_token(self, email: str, token: str) -> bool:
        val = redis.get(f"reset:{email}")
        return bool(val and val == token)

    def new_otp(self, email: str) -> str:
        code = f"{secrets.randbelow(900000)+100000}"
        redis.set(f"otp:{email}", code, ex=300) # 5 min
        return code

    def verify_otp(self, email: str, otp: str) -> bool:
        val = redis.get(f"otp:{email}")
        if val and val == otp:
            redis.delete(f"otp:{email}")
            return True
        return False
