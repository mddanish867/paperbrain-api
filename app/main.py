from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
import json
import os

# Import settings first
from app.core.config import settings

# Then import logger - this avoids circular imports
from app.utils.logger import logger

# Then import other modules
from app.db.base import Base
from app.db.session import engine
from app.api.v1 import auth, chat, documents
from app.middleware.rate_limit import rate_limit_middleware
from app.services.analytics import analytics_service
from app.services.cache import cache_service
from app.services.chat import ChatService
from app.services.document_processor import DocumentProcessor
from app.services.vector_store import get_vector_store

# Create database tables
Base.metadata.create_all(bind=engine)

# Initialize FastAPI app
app = FastAPI(
    title=settings.APP_NAME,
    description="AI Document Search with Retrieval-Augmented Generation",
    version="1.0.0",
    docs_url="/docs" if settings.DEBUG else None,
    redoc_url="/redoc" if settings.DEBUG else None,
)

# Add rate limiting middleware
app.middleware("http")(rate_limit_middleware)

# Configure CORS
try:
    origins = json.loads(settings.CORS_ORIGINS) if isinstance(settings.CORS_ORIGINS, str) else settings.CORS_ORIGINS
except json.JSONDecodeError:
    origins = ["*"]
    logger.warning("Failed to parse CORS_ORIGINS, using default origins")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(auth.router)
app.include_router(chat.router)
app.include_router(documents.router)

# Dependency injections
def get_chat_service():
    return ChatService(
        vector_store=get_vector_store(),
        cache=cache_service,
        analytics=analytics_service
    )

def get_document_processor():
    return DocumentProcessor()

@app.on_event("startup")
async def startup_event():
    """Initialize services on startup"""
    logger.info(f"Starting {settings.APP_NAME} in {settings.APP_ENV} mode")
    
    # Test Redis connection
    try:
        redis_ping = cache_service.redis_client.ping()
        logger.info("Redis connection successful")
    except Exception as e:
        logger.error(f"Redis connection failed: {e}")
    
    # Test database connection
    try:
        with engine.connect() as conn:
            logger.info("Database connection successful")
    except Exception as e:
        logger.error(f"Database connection failed: {e}")
    
    # Initialize vector store
    try:
        vector_store = get_vector_store()
        logger.info(f"Vector store initialized: {vector_store.get_stats()}")
    except Exception as e:
        logger.error(f"Vector store initialization failed: {e}")
    
    # Validate email configuration
    email_validation = settings.validate_email_config()
    if email_validation['valid']:
        logger.info("Email configuration validated successfully")
        if email_validation['warnings']:
            for warning in email_validation['warnings']:
                logger.warning(f"Email config warning: {warning}")
    else:
        logger.warning("⚠️  Email configuration validation failed - email functionality may not work")

@app.get("/")
async def root():
    return {
        "message": f"{settings.APP_NAME} is running!",
        "version": "1.0.0",
        "environment": settings.APP_ENV,
        "endpoints": {
            "auth": "/auth/*",
            "chat": "/chat",
            "documents": "/documents",
            "docs": "/docs" if settings.DEBUG else "disabled"
        }
    }

@app.get("/health")
async def health_check():
    # Check essential services
    services_status = {
        "database": False,
        "redis": False,
        "vector_store": False
    }
    
    try:
        with engine.connect() as conn:
            services_status["database"] = True
    except:
        pass
    
    try:
        services_status["redis"] = cache_service.redis_client.ping()
    except:
        pass
    
    try:
        vector_store = get_vector_store()
        services_status["vector_store"] = True
    except:
        pass
    
    return {
        "status": "healthy" if all(services_status.values()) else "degraded",
        "message": f"{settings.APP_NAME} is running",
        "environment": settings.APP_ENV,
        "services": services_status
    }

@app.get("/stats")
async def get_stats():
    """Get system statistics"""
    try:
        vector_store = get_vector_store()
        vector_stats = vector_store.get_stats()
        
        # Get analytics stats
        analytics_stats = analytics_service.get_usage_stats()
        
        return {
            "vector_store": vector_stats,
            "analytics": analytics_stats,
            "cache": {
                "redis_connected": cache_service.redis_client.ping() if hasattr(cache_service, 'redis_client') else False
            }
        }
    except Exception as e:
        logger.error(f"Error getting stats: {e}")
        return {"error": str(e)}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.DEBUG,
        log_level="debug" if settings.DEBUG else "info"
    )