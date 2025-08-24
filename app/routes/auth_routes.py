from fastapi import APIRouter, Depends, HTTPException, status, Request
from typing import Annotated
from pydantic import BaseModel, EmailStr, constr
from sqlalchemy.orm import Session
from app.services.db import get_db
from app.models.user import User
from app.services.auth import AuthService
from app.services.email_service import email_service
from app.middleware.rate_limit import RateLimiter
from app.services.redis_client import redis  # assuming you made a redis wrapper

router = APIRouter(prefix="/auth", tags=["auth"])
auth = AuthService()
rate = RateLimiter()

# Schemas
class RegisterReq(BaseModel):
    username: Annotated[str, constr(min_length=3, max_length=50)]
    email: EmailStr
    password: Annotated[str, constr(min_length=8)]

class LoginReq(BaseModel):
    username_or_email: str
    password: str

class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"

class VerifyEmailReq(BaseModel):
    email: EmailStr
    token: str

class ForgotReq(BaseModel):
    email: EmailStr

class ResetReq(BaseModel):
    email: EmailStr
    token: str
    new_password: Annotated[str, constr(min_length=8)]

class OTPVerifyReq(BaseModel):
    email: EmailStr
    otp: Annotated[str, constr(min_length=6, max_length=6)]

class RefreshReq(BaseModel):
    refresh_token: str


def rl_dep(request: Request):
    ip = request.client.host if request and request.client else "unknown"
    rate.check_rate_limit(ip)


@router.post("/register", response_model=TokenPair, dependencies=[Depends(rl_dep)])
def register(payload: RegisterReq, db: Session = Depends(get_db)):
    if db.query(User).filter((User.username == payload.username) | (User.email == payload.email)).first():
        raise HTTPException(status_code=400, detail="User already exists")

    user = User(
        username=payload.username,
        email=payload.email,
        password_hash=auth.hash_password(payload.password)
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    # email verification
    token = auth.new_verify_email_token(user.email)
    link = f"https://your-frontend/verify-email?email={user.email}&token={token}"
    email_service.send(
        user.email,
        "Verify your email",
        f"<p>Hi {user.username},</p><p><a href='{link}'>Verify Email</a></p>"
    )

    access, refresh = auth.create_tokens(sub=user.username)
    return TokenPair(access_token=access, refresh_token=refresh)


@router.post("/login", response_model=TokenPair, dependencies=[Depends(rl_dep)])
def login(payload: LoginReq, db: Session = Depends(get_db)):
    user = (
        db.query(User)
        .filter((User.username == payload.username_or_email) | (User.email == payload.username_or_email))
        .first()
    )
    if not user or not auth.verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    access, refresh = auth.create_tokens(sub=user.username)
    return TokenPair(access_token=access, refresh_token=refresh)


@router.post("/verify-email", dependencies=[Depends(rl_dep)])
def verify_email(payload: VerifyEmailReq, db: Session = Depends(get_db)):
    if not auth.check_verify_email_token(payload.email, payload.token):
        raise HTTPException(status_code=400, detail="Invalid or expired token")

    user = db.query(User).filter(User.email == payload.email).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user.email_verified = True
    db.commit()
    return {"message": "Email verified"}


@router.post("/forgot-password", dependencies=[Depends(rl_dep)])
def forgot_password(payload: ForgotReq, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == payload.email).first()
    # Always respond success (do not leak existence)
    if user:
        token = auth.new_reset_token(user.email)
        link = f"https://your-frontend/reset?email={user.email}&token={token}"
        email_service.send(
            user.email,
            "Password reset",
            f"<p>Reset your password:</p><p><a href='{link}'>Reset</a></p>"
        )
    return {"message": "If that email exists, we sent instructions."}


@router.post("/reset-password", dependencies=[Depends(rl_dep)])
def reset_password(payload: ResetReq, db: Session = Depends(get_db)):
    if not auth.check_reset_token(payload.email, payload.token):
        raise HTTPException(status_code=400, detail="Invalid or expired token")

    user = db.query(User).filter(User.email == payload.email).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user.password_hash = auth.hash_password(payload.new_password)
    db.commit()
    return {"message": "Password updated"}


@router.post("/verify-otp", dependencies=[Depends(rl_dep)])
def verify_otp(payload: OTPVerifyReq):
    if auth.verify_otp(payload.email, payload.otp):
        return {"message": "OTP verified"}
    raise HTTPException(status_code=400, detail="Invalid or expired OTP")


@router.post("/refresh", response_model=TokenPair, dependencies=[Depends(rl_dep)])
def refresh(payload: RefreshReq):
    data = auth.decode_token(payload.refresh_token)
    if data.get("type") != "refresh":
        raise HTTPException(status_code=400, detail="Not a refresh token")

    key = f"refresh:{data['sub']}:{payload.refresh_token[-16:]}"
    if not redis.get(key):
        raise HTTPException(status_code=401, detail="Refresh token not recognized")

    access, refresh = auth.create_tokens(sub=data["sub"])
    return TokenPair(access_token=access, refresh_token=refresh)
