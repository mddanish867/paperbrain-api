from fastapi import APIRouter, HTTPException
from app.services.chat import chat_service
from app.db.models.chat import ChatRequest, ChatResponse, ConversationHistory

router = APIRouter(prefix="/chat", tags=["chat"])

@router.post("", response_model=ChatResponse)
async def chat(request: ChatRequest):
    try:
        response = await chat_service.get_response(
            message=request.message,
            session_id=request.session_id or "default"
        )
        return ChatResponse(**response)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Chat error: {str(e)}")

@router.get("/history/{session_id}", response_model=ConversationHistory)
async def get_chat_history(session_id: str):
    history = chat_service.get_conversation_history(session_id)
    return ConversationHistory(messages=history, session_id=session_id)

@router.delete("/history/{session_id}")
async def clear_chat_history(session_id: str):
    chat_service.clear_conversation_history(session_id)
    return {"message": f"Chat history cleared for session {session_id}"}

@router.get("/sessions")
async def list_sessions():
    return {"sessions": []}

@router.get("/session/{session_id}/info")
async def get_session_info(session_id: str):
    session_info = chat_service.get_session_info(session_id)
    if not session_info:
        raise HTTPException(status_code=404, detail="Session not found")
    return session_info
