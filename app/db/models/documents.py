from pydantic import BaseModel
from typing import List, Optional

class DocumentUploadResponse(BaseModel):
    id: str
    filename: str
    chunk_count: int
    session_id: str  # ✅ New field for document-specific sessions

class DocumentListResponse(BaseModel):
    doc_id: str
    filename: str
    chunk_count: int

class DocumentDeleteResponse(BaseModel):
    success: bool
    message: str