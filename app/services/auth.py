from sqlalchemy.orm import Session
from fastapi import HTTPException, status, Depends, BackgroundTasks
from fastapi.security import HTTPBearer
from jose import JWTError
import threading

from app.db.models.user import User
from app.core.security import (
    verify_password, 
    get_password_hash, 
    create_access_token, 
    create_refresh_token,
    decode_token,
    get_current_user,
    generate_otp
)
from app.db.session import get_db
from app.services.email import email_service
from app.utils.logger import logger

security = HTTPBearer()

class AuthService:
    def __init__(self, db: Session):
        self.db = db

    def authenticate_user(self, username: str, password: str) -> User:
        """
        Authenticate user with username/email and password
        """
        user = self.db.query(User).filter(
            (User.username == username) | (User.email == username)
        ).first()
        
        if not user or not verify_password(password, user.password_hash):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid credentials",
            )
        
        if not user.email_verified:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Email not verified. Please verify your email before logging in.",
            )
            
        return user

    def register_user(self, username: str, email: str, password: str) -> User:
        """
        Register a new user and send verification email
        """
        # Check if user already exists
        existing_user = self.db.query(User).filter(
            (User.username == username) | (User.email == email)
        ).first()
        
        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="User with this username or email already exists",
            )
        
        # Create new user
        user = User(
            username=username,
            email=email,
            password_hash=get_password_hash(password),
        )
        
        try:
            self.db.add(user)
            self.db.commit()
            self.db.refresh(user)
            logger.info(f"New user registered: {username} ({email})")
            
        except Exception as e:
            self.db.rollback()
            logger.error(f"Failed to register user {username}: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to create user account"
            )
        
        return user

    def send_verification_email(self, user: User):
        """
        Send verification email to user (runs in background thread)
        """
        try:
            # Generate OTP
            otp = generate_otp(user.email)
            
            # Send verification email
            success = email_service.send_verification_email(user.email, user.username, otp)
            
            if success:
                logger.info(f"Verification email sent to {user.email}")
            else:
                logger.error(f"Failed to send verification email to {user.email}")
                
        except Exception as e:
            logger.error(f"Error sending verification email to {user.email}: {e}")

    def send_welcome_email(self, user: User):
        """
        Send welcome email after successful verification (runs in background thread)
        """
        try:
            success = email_service.send_welcome_email(user.email, user.username)
            
            if success:
                logger.info(f"Welcome email sent to {user.email}")
            else:
                logger.error(f"Failed to send welcome email to {user.email}")
                
        except Exception as e:
            logger.error(f"Error sending welcome email to {user.email}: {e}")

    def verify_user_email(self, email: str, otp: str) -> User:
        """
        Verify user email with OTP
        """
        from app.core.security import verify_otp
        
        if not verify_otp(email, otp):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid or expired OTP.",
            )
        
        user = self.db.query(User).filter(User.email == email).first()
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found.",
            )
        
        if user.email_verified:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email is already verified.",
            )
        
        # Update user verification status
        user.email_verified = True
        
        try:
            self.db.commit()
            logger.info(f"User email verified: {email}")
            
            # Send welcome email in background
            self._send_email_in_background(self.send_welcome_email, user)
            
        except Exception as e:
            self.db.rollback()
            logger.error(f"Failed to verify email for {email}: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to verify email"
            )
        
        return user

    def resend_verification_email(self, email: str):
        """
        Resend verification email
        """
        user = self.db.query(User).filter(User.email == email).first()
        
        # Always return success to prevent email enumeration
        if user and not user.email_verified:
            # Send verification email in background
            self._send_email_in_background(self.send_verification_email, user)
            logger.info(f"Verification email re-sent to {email}")
        
        return True

    def initiate_password_reset(self, email: str):
        """
        Initiate password reset process
        """
        from app.core.security import generate_reset_token
        
        user = self.db.query(User).filter(User.email == email).first()
        
        # Always return success to prevent email enumeration
        if user:
            # Generate reset token
            reset_token = generate_reset_token(user.email)
            
            # Send password reset email in background
            self._send_password_reset_email(user, reset_token)
            logger.info(f"Password reset initiated for {email}")
        
        return True

    def _send_password_reset_email(self, user: User, reset_token: str):
        """
        Send password reset email (runs in background thread)
        """
        try:
            success = email_service.send_password_reset_email(user.email, user.username, reset_token)
            
            if success:
                logger.info(f"Password reset email sent to {user.email}")
            else:
                logger.error(f"Failed to send password reset email to {user.email}")
                
        except Exception as e:
            logger.error(f"Error sending password reset email to {user.email}: {e}")

    def reset_password(self, email: str, token: str, new_password: str) -> bool:
        """
        Reset user password with token
        """
        from app.core.security import verify_reset_token
        
        if not verify_reset_token(email, token):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid or expired password reset token.",
            )
        
        user = self.db.query(User).filter(User.email == email).first()
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found.",
            )
        
        # Update password
        user.password_hash = get_password_hash(new_password)
        
        try:
            self.db.commit()
            logger.info(f"Password reset for user: {email}")
            return True
            
        except Exception as e:
            self.db.rollback()
            logger.error(f"Failed to reset password for {email}: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to reset password"
            )

    def _send_email_in_background(self, email_func, *args, **kwargs):
        """
        Helper method to send emails in background threads
        """
        def email_worker():
            try:
                email_func(*args, **kwargs)
            except Exception as e:
                logger.error(f"Background email task failed: {e}")
        
        # Start background thread for email sending
        email_thread = threading.Thread(target=email_worker)
        email_thread.daemon = True  # Thread will exit when main thread exits
        email_thread.start()

    def create_tokens(self, username: str) -> tuple[str, str]:
        """
        Create access and refresh tokens for user
        """
        access_token = create_access_token({"sub": username})
        refresh_token = create_refresh_token({"sub": username})
        return access_token, refresh_token

    def refresh_tokens(self, refresh_token: str) -> tuple[str, str]:
        """
        Refresh access token using refresh token
        """
        try:
            payload = decode_token(refresh_token)
            if payload.get("type") != "refresh":
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid token type",
                )
            
            username = payload.get("sub")
            if not username:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid token",
                )
                
            return self.create_tokens(username)
            
        except JWTError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid refresh token",
            )

    def get_user_by_email(self, email: str) -> User:
        """
        Get user by email address
        """
        return self.db.query(User).filter(User.email == email).first()

    def get_user_by_username(self, username: str) -> User:
        """
        Get user by username
        """
        return self.db.query(User).filter(User.username == username).first()

    def update_user_profile(self, user: User, update_data: dict) -> User:
        """
        Update user profile information
        """
        for key, value in update_data.items():
            if hasattr(user, key) and key not in ['id', 'email_verified', 'created_at', 'updated_at']:
                setattr(user, key, value)
        
        try:
            self.db.commit()
            self.db.refresh(user)
            logger.info(f"User profile updated: {user.username}")
            return user
            
        except Exception as e:
            self.db.rollback()
            logger.error(f"Failed to update user profile {user.username}: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to update profile"
            )

def get_auth_service(db: Session = Depends(get_db)) -> AuthService:
    return AuthService(db)