import os
from typing import Dict, List, Optional
from app.core.config import settings
from app.services.vector_store import get_vector_store
from app.services.redis import redis_client
from app.utils.logger import logger
import json
import hashlib
from datetime import datetime

class ChatService:
    def __init__(self, vector_store=None, analytics_service=None):
        self.vector_store = vector_store or get_vector_store()
        self.analytics_service = analytics_service
        
        if not settings.GEMINI_API_KEY:
            logger.warning("GEMINI_API_KEY not found. Chat service will not work properly.")
            self.client = None
        else:
            # Initialize Google Gemini client
            try:
                import google.generativeai as genai
                genai.configure(api_key=settings.GEMINI_API_KEY)
                self.client = genai.GenerativeModel(settings.GEMINI_MODEL)
                logger.info(f"Initialized Gemini client with model: {settings.GEMINI_MODEL}")
            except ImportError:
                logger.error("google-generativeai package not installed. Install with: pip install google-generativeai")
                self.client = None
            except Exception as e:
                logger.error(f"Error initializing Gemini client: {e}")
                self.client = None
        
        self.model_name = settings.GEMINI_MODEL
        self.temperature = settings.GEMINI_TEMPERATURE
        self.max_tokens = settings.GEMINI_MAX_TOKENS

    async def create_document_session(self, doc_id: str, filename: str) -> str:
        """Create a new chat session specifically for a document"""
        import uuid
        
        session_id = f"doc_{uuid.uuid4().hex[:12]}"
        
        # Store session metadata in Redis
        session_data = {
            "session_id": session_id,
            "doc_id": doc_id,
            "filename": filename,
            "created_at": datetime.utcnow().isoformat(),
            "type": "document"  # To distinguish from general chats
        }
        
        try:
            # Store session metadata
            redis_client.setex(
                f"session:{session_id}", 
                24 * 3600 * 7,  # 7 days expiration
                json.dumps(session_data)
            )
            logger.info(f"Created document session {session_id} for doc {doc_id}")
            return session_id
        except Exception as e:
            logger.error(f"Failed to create session: {e}")
            # Fallback: still return a session_id but it won't have Redis metadata
            return session_id

    async def get_response(self, message: str, session_id: str = "default") -> Dict:
        # Check if this is a document-specific session
        doc_id = None
        session_info = None
        
        try:
            session_data = redis_client.get(f"session:{session_id}")
            if session_data:
                session_info = json.loads(session_data)
                doc_id = session_info.get("doc_id")
                if doc_id:
                    logger.info(f"Using document context from session: {doc_id} for document: {session_info.get('filename', 'Unknown')}")
        except Exception as e:
            logger.warning(f"Error reading session data for {session_id}: {e}")

        # Check cache first (modify cache key to include doc_id if present)
        cache_key = f"query:{hashlib.md5(message.encode()).hexdigest()}:{doc_id or 'general'}"
        cached_response = self._get_cached_response(cache_key)
        if cached_response:
            if self.analytics_service:
                self.analytics_service.track_event("chat_cache_hit", metadata={"session_id": session_id})
            logger.info("Cache hit for chat query")
            self._append_to_conversation(session_id, message, cached_response)
            return cached_response

        if not self.client:
            return {
                "response": "Gemini API not configured. Please set GEMINI_API_KEY and install google-generativeai package.", 
                "sources": []
            }

        try:
            # ✅ MODIFIED: Use document-filtered search if doc_id is available
            if doc_id:
                logger.info(f"Searching within document: {doc_id}")
                # Search only within the specific document
                if hasattr(self.vector_store, 'search_with_filter'):
                    relevant_chunks = await self.vector_store.search_with_filter(
                        query=message, 
                        k=5,
                        filter_dict={"doc_id": doc_id}
                    )
                    logger.info(f"Document-filtered search returned {len(relevant_chunks)} chunks")
                else:
                    # Fallback: regular search (will search all documents)
                    relevant_chunks = await self.vector_store.search(message, k=5)
                    logger.warning("Vector store doesn't support filtered search, using regular search")
                    logger.info(f"Regular search returned {len(relevant_chunks)} chunks")
            else:
                logger.info("Performing general search across all documents")
                # General search across all documents
                relevant_chunks = await self.vector_store.search(message, k=5)
                logger.info(f"General search returned {len(relevant_chunks)} chunks")
                
            if not relevant_chunks:
                # Additional debugging
                stats = self.vector_store.get_stats()
                logger.warning(f"No relevant chunks found. Vector store stats: {stats}")
                
                if doc_id:
                    return {
                        "response": f"No relevant content found in the document (doc_id: {doc_id}). The document may be empty or the search query didn't match any content.", 
                        "sources": []
                    }
                else:
                    return {
                        "response": "No documents available. Upload a PDF via /upload first.", 
                        "sources": []
                    }

            # Build context
            context_pieces, source_info = [], []
            for i, chunk in enumerate(relevant_chunks):
                context_pieces.append(f"Document {i+1}: {chunk['text']}")
                source_info.append({
                    "filename": chunk.get('filename', 'Unknown'),
                    "chunk_index": chunk.get('chunk_index', 0),
                    "similarity_score": float(chunk.get('similarity_score', 0.0))
                })
            context = "\n\n".join(context_pieces)

            # Create prompt for Gemini
            prompt = f"""You are a helpful AI assistant answering strictly from the provided context.
If the answer isn't in the context, say so clearly. Be concise and cite relevant parts.

Context:
{context}

Question: {message}

Answer from the context above:"""

            # Call Gemini API
            logger.info("Calling Gemini API...")
            
            # Configure generation parameters
            generation_config = {
                "temperature": self.temperature,
                "max_output_tokens": self.max_tokens,
            }
            
            # Generate response
            response = self.client.generate_content(
                prompt,
                generation_config=generation_config
            )
            
            # Extract the text response
            if response.text:
                ai_response = response.text.strip()
            else:
                # Handle potential safety filtering or other issues
                if hasattr(response, 'prompt_feedback'):
                    logger.warning(f"Gemini prompt feedback: {response.prompt_feedback}")
                if hasattr(response, 'candidates') and response.candidates:
                    candidate = response.candidates[0]
                    if hasattr(candidate, 'finish_reason'):
                        logger.warning(f"Gemini finish reason: {candidate.finish_reason}")
                
                ai_response = "I apologize, but I couldn't generate a response. This might be due to content safety filters or technical issues."
            
            result = {"response": ai_response, "sources": source_info}

            # Cache response with doc_id-aware key
            self._cache_response(cache_key, result)
            self._append_to_conversation(session_id, message, result)

            # Track analytics
            if self.analytics_service:
                self.analytics_service.track_event(
                    "chat_answered", 
                    metadata={
                        "session_id": session_id,
                        "model": self.model_name,
                        "sources_count": len(source_info),
                        "doc_id": doc_id or "general"
                    }
                )

            return result

        except Exception as e:
            logger.error(f"Chat error with Gemini: {e}")
            if self.analytics_service:
                self.analytics_service.track_event(
                    "chat_error", 
                    metadata={
                        "error": str(e), 
                        "session_id": session_id,
                        "model": self.model_name,
                        "doc_id": doc_id or "general"
                    }
                )
            
            # More specific error messages for common Gemini issues
            error_message = "Error processing your question"
            if "API_KEY_INVALID" in str(e):
                error_message = "Invalid Gemini API key. Please check your configuration."
            elif "QUOTA_EXCEEDED" in str(e):
                error_message = "Gemini API quota exceeded. Please try again later."
            elif "SAFETY" in str(e).upper():
                error_message = "Content was blocked by safety filters. Please rephrase your question."
            else:
                error_message = f"Error processing your question: {e}"
                
            return {"response": error_message, "sources": []}

    def _get_cached_response(self, cache_key: str) -> Optional[Dict]:
        try:
            cached = redis_client.get(cache_key)
            return json.loads(cached) if cached else None
        except Exception as e:
            logger.warning(f"Cache retrieval error: {e}")
            return None

    def _cache_response(self, cache_key: str, response: Dict, ttl: int = 3600):
        try:
            redis_client.setex(cache_key, ttl, json.dumps(response))
        except Exception as e:
            logger.warning(f"Cache storage error: {e}")

    def _append_to_conversation(self, session_id: str, question: str, response: Dict):
        conversation_key = f"convo:{session_id}"
        try:
            record = {
                "question": question,
                "answer": response["response"],
                "sources": [s["filename"] for s in response["sources"]],
                "context_chunks": len(response["sources"]),
                "model": self.model_name,
                "timestamp": datetime.utcnow().isoformat()
            }
            
            redis_client.rpush(conversation_key, json.dumps(record))
            
            # Trim conversation to last 10 messages
            length = redis_client.llen(conversation_key)
            if length > 10:
                redis_client.ltrim(conversation_key, length - 10, -1)
            
            # Set expiration (24 hours)
            redis_client.expire(conversation_key, 24 * 3600)
            
        except Exception as e:
            logger.warning(f"Conversation storage error: {e}")

    def get_conversation_history(self, session_id: str) -> List[Dict]:
        conversation_key = f"convo:{session_id}"
        try:
            raw_messages = redis_client.lrange(conversation_key, 0, -1) or []
            return [json.loads(msg) for msg in raw_messages]
        except Exception as e:
            logger.warning(f"Conversation retrieval error: {e}")
            return []

    def clear_conversation_history(self, session_id: str):
        conversation_key = f"convo:{session_id}"
        try:
            redis_client.delete(conversation_key)
            logger.info(f"Cleared conversation history for session: {session_id}")
        except Exception as e:
            logger.warning(f"Conversation clear error: {e}")
    
    def get_session_info(self, session_id: str) -> Optional[Dict]:
        """Get information about a specific session"""
        try:
            session_data = redis_client.get(f"session:{session_id}")
            if session_data:
                return json.loads(session_data)
        except Exception as e:
            logger.warning(f"Session info retrieval error: {e}")
        return None
    
    def get_model_info(self) -> Dict:
        """Get information about the current model configuration"""
        return {
            "provider": "google_gemini",
            "model": self.model_name,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "configured": self.client is not None
        }

chat_service = ChatService()