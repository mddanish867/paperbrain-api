import os
from typing import Dict, List, Optional
from openai import OpenAI
from app.core.config import settings
from app.services.vector_store import get_vector_store
from app.services.redis import redis_client
from app.utils.logger import logger

class ChatService:
    def __init__(self, vector_store=None, analytics_service=None):
        self.vector_store = vector_store or get_vector_store()
        self.analytics_service = analytics_service
        
        if not settings.OPENAI_API_KEY:
            logger.warning("OPENAI_API_KEY not found. Chat service will not work properly.")
            self.client = None
        else:
            self.client = OpenAI(api_key=settings.OPENAI_API_KEY)
        
        self.model = settings.OPENAI_CHAT_MODEL

    async def get_response(self, message: str, session_id: str = "default") -> Dict:
        # Check cache first
        cached_response = self._get_cached_response(message)
        if cached_response:
            if self.analytics_service:
                self.analytics_service.track_event("chat_cache_hit", metadata={"session_id": session_id})
            logger.info("Cache hit for chat query")
            self._append_to_conversation(session_id, message, cached_response)
            return cached_response

        if not self.client:
            return {"response": "OpenAI API key not configured. Please set OPENAI_API_KEY.", "sources": []}

        try:
            # Retrieve relevant chunks
            logger.info(f"RAG search for: {message[:100]}...")
            relevant_chunks = await self.vector_store.search(message, k=5)
            if not relevant_chunks:
                return {"response": "No documents available. Upload a PDF via /upload first.", "sources": []}

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

            # Create prompt
            system_prompt = (
                "You are a helpful AI assistant answering strictly from the provided context.\n"
                "If the answer isn't in the context, say so clearly. Be concise and cite relevant parts."
            )
            user_prompt = f"Context:\n{context}\n\nQuestion: {message}\n\nAnswer from the context above."

            # Call OpenAI
            logger.info("Calling OpenAI...")
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                max_tokens=500,
                temperature=0.7
            )
            
            ai_response = response.choices[0].message.content.strip()
            result = {"response": ai_response, "sources": source_info}

            # Cache response
            self._cache_response(message, result)
            self._append_to_conversation(session_id, message, result)

            # Track analytics
            if self.analytics_service:
                self.analytics_service.track_event("chat_answered", metadata={"session_id": session_id})

            return result

        except Exception as e:
            logger.error(f"Chat error: {e}")
            if self.analytics_service:
                self.analytics_service.track_event("chat_error", metadata={"error": str(e), "session_id": session_id})
            return {"response": f"Error processing your question: {e}", "sources": []}

    def _get_cached_response(self, query: str) -> Optional[Dict]:
        import json
        import hashlib
        
        cache_key = f"query:{hashlib.md5(query.encode()).hexdigest()}"
        cached = redis_client.get(cache_key)
        return json.loads(cached) if cached else None

    def _cache_response(self, query: str, response: Dict, ttl: int = 3600):
        import json
        import hashlib
        
        cache_key = f"query:{hashlib.md5(query.encode()).hexdigest()}"
        redis_client.setex(cache_key, ttl, json.dumps(response))

    def _append_to_conversation(self, session_id: str, question: str, response: Dict):
        import json
        
        conversation_key = f"convo:{session_id}"
        record = {
            "question": question,
            "answer": response["response"],
            "sources": [s["filename"] for s in response["sources"]],
            "context_chunks": len(response["sources"])
        }
        
        redis_client.rpush(conversation_key, json.dumps(record))
        
        # Trim conversation to last 10 messages
        length = redis_client.llen(conversation_key)
        if length > 10:
            redis_client.ltrim(conversation_key, length - 10, -1)
        
        # Set expiration (24 hours)
        redis_client.expire(conversation_key, 24 * 3600)

    def get_conversation_history(self, session_id: str) -> List[Dict]:
        import json
        
        conversation_key = f"convo:{session_id}"
        raw_messages = redis_client.lrange(conversation_key, 0, -1) or []
        return [json.loads(msg) for msg in raw_messages]

    def clear_conversation_history(self, session_id: str):
        conversation_key = f"convo:{session_id}"
        redis_client.delete(conversation_key)