import re
from fastapi import HTTPException, status
from app.core.config import settings

def validate_file_size(file_size: int, max_size: int = None) -> None:
    max_size = max_size or settings.MAX_FILE_SIZE
    if file_size > max_size:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File too large. Maximum size is {max_size} bytes."
        )

def validate_query(query: str) -> None:
    if len(query) > 1000:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Query too long. Maximum length is 1000 characters."
        )
    
    # Basic SQL injection prevention
    dangerous_patterns = ['DROP', 'DELETE', 'UPDATE', 'INSERT', '--', ';', '/*', '*/', 'xp_']
    query_upper = query.upper()
    for pattern in dangerous_patterns:
        if pattern in query_upper:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid query content."
            )

def sanitize_filename(filename: str) -> str:
    # Remove dangerous characters and path traversal attempts
    filename = re.sub(r'[^a-zA-Z0-9._-]', '', filename)
    filename = re.sub(r'\.\.+', '.', filename)
    return filename

def validate_email(email: str) -> None:
    email_regex = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    if not re.match(email_regex, email):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid email format."
        )

def validate_password(password: str) -> None:
    if len(password) < 8:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password must be at least 8 characters long."
        )
    
    if not any(char.isdigit() for char in password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password must contain at least one digit."
        )
    
    if not any(char.isupper() for char in password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password must contain at least one uppercase letter."
        )
    
    if not any(char.islower() for char in password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password must contain at least one lowercase letter."
        )