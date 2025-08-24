import re
from fastapi import HTTPException

def validate_file_size(file_size: int, max_size: int = 10 * 1024 * 1024):  # 10MB
    if file_size > max_size:
        raise HTTPException(status_code=413, detail="File too large")

def validate_query(query: str):
    if len(query) > 1000:
        raise HTTPException(status_code=400, detail="Query too long")
    
    # Basic SQL injection prevention
    dangerous_patterns = ['DROP', 'DELETE', 'UPDATE', 'INSERT', '--', ';']
    query_upper = query.upper()
    for pattern in dangerous_patterns:
        if pattern in query_upper:
            raise HTTPException(status_code=400, detail="Invalid query")

def sanitize_filename(filename: str) -> str:
    # Remove dangerous characters
    return re.sub(r'[^a-zA-Z0-9._-]', '', filename)