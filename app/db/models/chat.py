from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from datetime import datetime

class ChatMessage(BaseModel):
    role: str  # "user" or "assistant"
    content: str
    timestamp: datetime

class SourceInfo(BaseModel):
    filename: str
    chunk_index: int
    similarity_score: float

class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = "default"

class ChatResponse(BaseModel):
    response: str
    sources: List[SourceInfo] = []

class ConversationHistory(BaseModel):
    session_id: str
    messages: List[Dict[str, Any]]

class ConversationRecord(BaseModel):
    question: str
    answer: str
    sources: List[str]
    context_chunks: int
    model: str
    timestamp: str

class SessionInfo(BaseModel):
    session_id: str
    doc_id: Optional[str] = None
    filename: Optional[str] = None
    created_at: str
    type: str  # "document" or "general"

class ModelInfo(BaseModel):
    provider: str
    model: str
    temperature: float
    max_tokens: int
    configured: bool