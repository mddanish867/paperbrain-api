import os
import json
import hashlib
import uuid
from datetime import datetime
from typing import Dict, List, Optional
from app.core.config import settings
from app.services.vector_store import get_vector_store
from app.services.redis import redis_client
from app.utils.logger import logger

class ChatService:
    def __init__(self, vector_store=None, analytics_service=None):
        self.vector_store = vector_store or get_vector_store()
        self.analytics_service = analytics_service

        if not settings.GEMINI_API_KEY:
            logger.warning("GEMINI_API_KEY not found. Chat service will not work properly.")
            self.client = None
        else:
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
        session_id = f"doc_{uuid.uuid4().hex[:12]}"
        session_data = {
            "session_id": session_id,
            "doc_id": doc_id,
            "filename": filename,
            "created_at": datetime.utcnow().isoformat(),
            "type": "document"
        }
        try:
            redis_client.setex(f"session:{session_id}", 24*3600*7, json.dumps(session_data))
            logger.info(f"Created document session {session_id} for doc {doc_id}")
            return session_id
        except Exception as e:
            logger.error(f"Failed to create session: {e}")
            return session_id

    async def get_response(self, message: str, session_id: str = "default") -> Dict:
        doc_id = None
        session_info = None
        try:
            session_data = redis_client.get(f"session:{session_id}")
            if session_data:
                session_info = json.loads(session_data)
                doc_id = session_info.get("doc_id")
                if doc_id:
                    logger.info(f"Using document context from session: {doc_id}")
        except Exception as e:
            logger.warning(f"Error reading session data for {session_id}: {e}")

        cache_key = f"query:{hashlib.md5(message.encode()).hexdigest()}:{doc_id or 'general'}"
        cached_response = self._get_cached_response(cache_key)
        if cached_response:
            if self.analytics_service:
                self.analytics_service.track_event("chat_cache_hit", metadata={"session_id": session_id})
            logger.info("Cache hit for chat query")
            self._append_to_conversation(session_id, message, cached_response)
            return cached_response

        if not self.client:
            return {"response": "Gemini API not configured.", "sources": []}

        try:
            if doc_id:
                if hasattr(self.vector_store, 'search_with_filter'):
                    relevant_chunks = await self.vector_store.search_with_filter(
                        query=message, k=5, filter_dict={"doc_id": doc_id}
                    )
                    logger.info(f"Document-filtered search returned {len(relevant_chunks)} chunks")
                else:
                    relevant_chunks = await self.vector_store.search(message, k=5)
                    logger.warning("Vector store doesn't support filtered search, using regular search")
            else:
                relevant_chunks = await self.vector_store.search(message, k=5)
                logger.info(f"General search returned {len(relevant_chunks)} chunks")

            if not relevant_chunks:
                return {"response": f"No relevant content found for doc_id: {doc_id or 'general'}", "sources": []}

            context_pieces, source_info = [], []
            for i, chunk in enumerate(relevant_chunks):
                context_pieces.append(f"Document {i+1}: {chunk['text']}")
                source_info.append({
                    "filename": chunk.get('filename', 'Unknown'),
                    "chunk_index": chunk.get('chunk_index', 0),
                    "similarity_score": float(chunk.get('similarity_score', 0.0))
                })
            context = "\n\n".join(context_pieces)

            prompt = f"""You are a helpful AI assistant answering strictly from the provided context.
If the answer isn't in the context, say so clearly. Be concise and cite relevant parts.

Context:
{context}

Question: {message}

Answer from the context above:"""

            generation_config = {"temperature": self.temperature, "max_output_tokens": self.max_tokens}
            response = self.client.generate_content(prompt, generation_config=generation_config)
            ai_response = response.text.strip() if response.text else "I couldn't generate a response."

            result = {"response": ai_response, "sources": source_info}
            self._cache_response(cache_key, result)
            self._append_to_conversation(session_id, message, result)

            if self.analytics_service:
                self.analytics_service.track_event(
                    "chat_answered",
                    metadata={"session_id": session_id, "model": self.model_name,
                              "sources_count": len(source_info), "doc_id": doc_id or "general"}
                )

            return result

        except Exception as e:
            logger.error(f"Chat error: {e}")
            return {"response": f"Error processing your question: {e}", "sources": []}

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
            length = redis_client.llen(conversation_key)
            if length > 10:
                redis_client.ltrim(conversation_key, length - 10, -1)
            redis_client.expire(conversation_key, 24*3600)
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
        try:
            redis_client.delete(f"convo:{session_id}")
            logger.info(f"Cleared conversation history for session: {session_id}")
        except Exception as e:
            logger.warning(f"Conversation clear error: {e}")

    def get_session_info(self, session_id: str) -> Optional[Dict]:
        try:
            session_data = redis_client.get(f"session:{session_id}")
            return json.loads(session_data) if session_data else None
        except Exception as e:
            logger.warning(f"Session info retrieval error: {e}")
            return None

    def get_model_info(self) -> Dict:
        return {
            "provider": "google_gemini",
            "model": self.model_name,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "configured": self.client is not None
        }

chat_service = ChatService()
