from fastapi import FastAPI, File, UploadFile, HTTPException, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import BaseModel
import os
import tempfile
from dotenv import load_dotenv

# Services & utils
from app.services.document_processor import DocumentProcessor
from app.services.vector_store import VectorStore
from app.services.chat_service import ChatService
from app.services.auth import AuthService, security
from app.services.cache import CacheService
from app.services.analytics import AnalyticsService
from app.middleware.rate_limit import RateLimiter
from app.utils.logger import logger
from app.utils.validators import validate_file_size, validate_query, sanitize_filename

# NEW: DB + auth routes
from app.services.db import Base, engine
from app.routes.auth_routes import router as auth_router

load_dotenv()

app = FastAPI(
    title="RAG Chatbot API",
    description="AI Document Search with Retrieval-Augmented Generation",
    version="1.2.0"
)

# CORS
cors_origins = os.getenv("CORS_ORIGINS", '["*"]').strip()
try:
    import json as _json
    parsed_origins = _json.loads(cors_origins)
    if not isinstance(parsed_origins, list):
        parsed_origins = ["*"]
except Exception:
    parsed_origins = ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=parsed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize core services
logger.info("Initializing services...")
document_processor = DocumentProcessor()
vector_store = VectorStore()
cache_service = CacheService()
analytics_service = AnalyticsService()
auth_service = AuthService()
chat_service = ChatService(
    vector_store=vector_store,
    cache=cache_service,
    analytics=analytics_service,
    logger=logger
)
rate_limiter = RateLimiter()
logger.info("Services initialized successfully!")

# ---- DB tables on startup
@app.on_event("startup")
def on_startup():
    Base.metadata.create_all(bind=engine)

# Dependencies
def rate_limit_dep(request: Request):
    client_ip = request.client.host if request and request.client else "unknown"
    rate_limiter.check_rate_limit(client_ip)

def require_auth(credentials: HTTPAuthorizationCredentials = Depends(security)):
    return auth_service.verify_token(credentials)

# Pydantic models
class ChatRequest(BaseModel):
    message: str
    session_id: str = "default"

class ChatResponse(BaseModel):
    response: str
    sources: list = []

class UploadResponse(BaseModel):
    message: str
    document_id: str
    filename: str
    chunks_count: int

class LoginRequest(BaseModel):
    username: str
    password: str

class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"

@app.get("/")
async def root():
    return {
        "message": "RAG Chatbot API is running!",
        "version": "1.2.0",
        "endpoints": {
            "auth": "/auth/*",
            "upload": "/upload",
            "chat": "/chat",
            "documents": "/documents",
            "health": "/health",
            "analytics": "/analytics"
        }
    }

# (Kept for backward-compat demos; prefer /auth/login for real)
@app.post("/login", response_model=LoginResponse)
async def login(payload: LoginRequest, _rl: None = Depends(rate_limit_dep)):
    if not payload.username or not payload.password:
        raise HTTPException(status_code=400, detail="Username and password required")
    # DEMO: just mint an access token (no DB check). Use /auth/login for real login.
    token = auth_service.create_access_token({"sub": payload.username})
    analytics_service.track_event("login_success", user_id=payload.username)
    logger.info(f"User '{payload.username}' logged in (demo /login)")
    return LoginResponse(access_token=token)

@app.post("/upload", response_model=UploadResponse, dependencies=[Depends(rate_limit_dep), Depends(require_auth)])
async def upload_document(file: UploadFile = File(...)):
    safe_filename = sanitize_filename(file.filename or "uploaded.pdf")
    logger.info(f"Received file upload: {safe_filename}")

    if not safe_filename.lower().endswith('.pdf'):
        analytics_service.track_event("upload_failed", metadata={"reason": "not_pdf", "filename": safe_filename})
        raise HTTPException(status_code=400, detail="Only PDF files are supported")

    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp_file:
            content = await file.read()
            validate_file_size(len(content))
            tmp_file.write(content)
            tmp_file_path = tmp_file.name

        logger.info(f"Saved temporary file: {tmp_file_path}")

        logger.info("Processing document...")
        chunks = document_processor.process_pdf(tmp_file_path, safe_filename)
        logger.info(f"Document processed into {len(chunks)} chunks")

        logger.info("Storing in vector database...")
        doc_id = await vector_store.store_document(chunks, safe_filename)
        logger.info(f"Document stored with ID: {doc_id}")

        os.unlink(tmp_file_path)

        analytics_service.track_event(
            "upload_success",
            metadata={"document_id": doc_id, "filename": safe_filename, "chunks": len(chunks)}
        )

        return UploadResponse(
            message="Document uploaded and processed successfully",
            document_id=doc_id,
            filename=safe_filename,
            chunks_count=len(chunks)
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error processing document: {str(e)}")
        analytics_service.track_event("upload_failed", metadata={"error": str(e), "filename": safe_filename})
        if 'tmp_file_path' in locals() and os.path.exists(tmp_file_path):
            os.unlink(tmp_file_path)
        raise HTTPException(status_code=500, detail=f"Error processing document: {str(e)}")

@app.post("/chat", response_model=ChatResponse, dependencies=[Depends(rate_limit_dep), Depends(require_auth)])
async def chat(request: ChatRequest):
    validate_query(request.message)
    logger.info(f"Chat request: {request.message[:100]}... (session={request.session_id})")

    try:
        response = await chat_service.get_response(request.message, request.session_id)
        logger.info(f"Generated response: {response['response'][:100]}...")
        analytics_service.track_event(
            "chat_success",
            metadata={"session_id": request.session_id, "msg_len": len(request.message)}
        )
        return ChatResponse(**response)
    except Exception as e:
        logger.error(f"Error in chat: {str(e)}")
        analytics_service.track_event(
            "chat_failed",
            metadata={"error": str(e), "session_id": request.session_id}
        )
        raise HTTPException(status_code=500, detail=f"Error generating response: {str(e)}")

@app.get("/documents", dependencies=[Depends(rate_limit_dep), Depends(require_auth)])
async def list_documents():
    try:
        documents = await vector_store.list_documents()
        analytics_service.track_event("documents_listed", metadata={"count": len(documents)})
        return {"documents": documents, "count": len(documents)}
    except Exception as e:
        logger.error(f"Error listing documents: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error listing documents: {str(e)}")

@app.delete("/documents/{doc_id}", dependencies=[Depends(rate_limit_dep), Depends(require_auth)])
async def delete_document(doc_id: str):
    try:
        await vector_store.delete_document(doc_id)
        analytics_service.track_event("document_deleted", metadata={"document_id": doc_id})
        return {"message": "Document deleted successfully", "document_id": doc_id}
    except Exception as e:
        logger.error(f"Error deleting document: {str(e)}")
        analytics_service.track_event("document_delete_failed", metadata={"document_id": doc_id, "error": str(e)})
        raise HTTPException(status_code=500, detail=f"Error deleting document: {str(e)}")

@app.get("/analytics", dependencies=[Depends(rate_limit_dep), Depends(require_auth)])
async def get_analytics():
    return analytics_service.get_usage_stats()

@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "message": "RAG Chatbot API is running",
        "services": {
            "document_processor": "OK",
            "vector_store": "OK",
            "chat_service": "OK",
            "cache": "OK",
            "analytics": "OK",
        }
    }

@app.get("/stats", dependencies=[Depends(rate_limit_dep), Depends(require_auth)])
async def get_stats():
    try:
        docs = await vector_store.list_documents()
        return {
            "total_documents": len(docs),
            "total_chunks": sum(doc.get('chunk_count', 0) for doc in docs),
            "vector_store_size": vector_store.index.ntotal if hasattr(vector_store, 'index') else 0
        }
    except Exception as e:
        logger.error(f"Error getting stats: {str(e)}")
        return {"error": str(e)}

# Mount auth routes (register/login/verify/forgot/reset/refresh)
app.include_router(auth_router)

if __name__ == "__main__":
    import uvicorn
    host = os.getenv("APP_HOST", "0.0.0.0")
    port = int(os.getenv("APP_PORT", 8000))
    uvicorn.run(app, host=host, port=port, reload=True)
