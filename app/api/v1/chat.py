from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from typing import List

from app.services.chat import ChatService
from app.core.security import get_current_user
from app.utils.validators import validate_query
from app.utils.logger import logger

router = APIRouter(prefix="/chat", tags=["chat"])

class ChatRequest(BaseModel):
    message: str
    session_id: str = "default"

class ChatResponse(BaseModel):
    response: str
    sources: List[dict] = []

class ConversationHistory(BaseModel):
    messages: List[dict]

@router.post("", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    chat_service: ChatService = Depends(ChatService),
    current_user: dict = Depends(get_current_user)
):
    validate_query(request.message)
    logger.info(f"Chat request from {current_user['sub']}: {request.message[:100]}...")
    
    response = await chat_service.get_response(request.message, request.session_id)
    return ChatResponse(**response)

@router.get("/history/{session_id}", response_model=ConversationHistory)
async def get_chat_history(
    session_id: str,
    chat_service: ChatService = Depends(ChatService),
    current_user: dict = Depends(get_current_user)
):
    history = chat_service.get_conversation_history(session_id)
    return ConversationHistory(messages=history)

@router.delete("/history/{session_id}")
async def clear_chat_history(
    session_id: str,
    chat_service: ChatService = Depends(ChatService),
    current_user: dict = Depends(get_current_user)
):
    chat_service.clear_conversation_history(session_id)
    return {"message": "Conversation history cleared"}