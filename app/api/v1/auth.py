from fastapi import APIRouter, Depends, HTTPException, status, Request, BackgroundTasks
from fastapi.security import HTTPBearer
from sqlalchemy.orm import Session
from pydantic import BaseModel, EmailStr, constr
from typing import Annotated, Optional
from app.services.email import email_service
import threading
from app.db.session import get_db
from app.db.models.user import User
from app.services.auth import AuthService, get_auth_service
from app.services.email import email_service
from app.core.security import (
    generate_otp, 
    verify_otp, 
    generate_reset_token, 
    verify_reset_token,
    get_current_user
)
from app.utils.validators import validate_email, validate_password
from app.utils.logger import logger

router = APIRouter(prefix="/auth", tags=["auth"])
security = HTTPBearer()

# Pydantic Models
class RegisterRequest(BaseModel):
    username: Annotated[str, constr(min_length=3, max_length=50, pattern="^[a-zA-Z0-9_]+$")]
    email: EmailStr
    password: Annotated[str, constr(min_length=8)]

class LoginRequest(BaseModel):
    username_or_email: str
    password: str

class OTPVerifyRequest(BaseModel):
    email: EmailStr
    otp: Annotated[str, constr(min_length=6, max_length=6, pattern="^[0-9]+$")]

class ResendOTPRequest(BaseModel):
    email: EmailStr

class ForgotPasswordRequest(BaseModel):
    email: EmailStr

class ResetPasswordRequest(BaseModel):
    email: EmailStr
    token: str
    new_password: Annotated[str, constr(min_length=8)]

class RefreshRequest(BaseModel):
    refresh_token: str

class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"

class AuthResponse(BaseModel):
    status_code: int
    message: str
    email: Optional[EmailStr] = None
    token: Optional[TokenResponse] = None

# Routes
@router.post("/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
async def register(
    payload: RegisterRequest, 
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    auth_service: AuthService = Depends(get_auth_service)
):
    # Validate email and password
    validate_email(payload.email)
    validate_password(payload.password)
    
    # Register user
    user = auth_service.register_user(payload.username, payload.email, payload.password)
    
    # Generate and send OTP
    otp = generate_otp(user.email)
    background_tasks.add_task(
        email_service.send_verification_email,
        user.email, user.username, otp
    )
    
    logger.info(f"New user registered: {user.username} ({user.email})")
    
    return AuthResponse(
        status_code=status.HTTP_201_CREATED,
        message="Registration successful. An OTP has been sent to your email for verification.",
        email=user.email
    )

@router.post("/verify-account", response_model=AuthResponse)
async def verify_account(
    payload: OTPVerifyRequest,
    db: Session = Depends(get_db),
    auth_service: AuthService = Depends(get_auth_service)
):
    if not verify_otp(payload.email, payload.otp):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired OTP."
        )
    
    user = db.query(User).filter(User.email == payload.email).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found."
        )
    
    if user.email_verified:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email is already verified."
        )
    
    user.email_verified = True
    db.commit()
    
    access_token, refresh_token = auth_service.create_tokens(user.username)
    
    logger.info(f"User email verified: {user.email}")
    
    return AuthResponse(
        status_code=status.HTTP_200_OK,
        message="Account verified successfully. You are now logged in.",
        email=user.email,
        token=TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token
        )
    )

@router.post("/resend-otp", status_code=status.HTTP_200_OK)
async def resend_otp(
    payload: ResendOTPRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    user = db.query(User).filter(User.email == payload.email).first()
    
    # Always return success to prevent email enumeration
    if user and not user.email_verified:
        otp = generate_otp(user.email)
        background_tasks.add_task(
            email_service.send_verification_email,
            user.email, user.username, otp
        )
    
    return {
        "status_code": status.HTTP_200_OK,
        "message": "If an unverified account with that email exists, a new OTP has been sent.",
        "email": payload.email
    }

@router.post("/login", response_model=AuthResponse)
async def login(
    payload: LoginRequest,
    auth_service: AuthService = Depends(get_auth_service)
):
    user = auth_service.authenticate_user(payload.username_or_email, payload.password)
    access_token, refresh_token = auth_service.create_tokens(user.username)
    
    logger.info(f"User logged in: {user.username}")
    
    return AuthResponse(
        status_code=status.HTTP_200_OK,
        message="Login successful.",
        email=user.email,
        token=TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token
        )
    )

@router.post("/forgot-password", status_code=status.HTTP_200_OK)
async def forgot_password(
    payload: ForgotPasswordRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    user = db.query(User).filter(User.email == payload.email).first()
    
    # Always return success to prevent email enumeration
    if user:
        reset_token = generate_reset_token(user.email)
        background_tasks.add_task(
            email_service.send_password_reset_email,
            user.email, user.username, reset_token
        )
    
    return {
        "status_code": status.HTTP_200_OK,
        "message": "If an account with that email exists, password reset instructions have been sent.",
        "email": payload.email
    }

@router.post("/reset-password", status_code=status.HTTP_200_OK)
async def reset_password(
    payload: ResetPasswordRequest,
    db: Session = Depends(get_db),
    auth_service: AuthService = Depends(get_auth_service)
):
    validate_password(payload.new_password)
    
    if not verify_reset_token(payload.email, payload.token):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired password reset token."
        )
    
    user = db.query(User).filter(User.email == payload.email).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found."
        )
    
    user.password_hash = auth_service.get_password_hash(payload.new_password)
    db.commit()
    
    logger.info(f"Password reset for user: {user.email}")
    
    return {
        "status_code": status.HTTP_200_OK,
        "message": "Your password has been updated successfully.",
        "email": payload.email
    }

@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(payload: RefreshRequest, auth_service: AuthService = Depends(get_auth_service)):
    access_token, refresh_token = auth_service.refresh_tokens(payload.refresh_token)
    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token
    )

@router.get("/me")
async def get_current_user_info(current_user: dict = Depends(get_current_user)):
    return {"username": current_user["sub"]}