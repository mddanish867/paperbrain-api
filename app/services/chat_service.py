from openai import OpenAI
import os
from typing import Dict, List

class ChatService:
    def __init__(self, vector_store, cache=None, analytics=None, logger=None):
        self.vector_store = vector_store
        self.cache = cache
        self.analytics = analytics
        self.logger = logger

        api_key = os.getenv('OPENAI_API_KEY')
        if not api_key and self.logger:
            self.logger.warning("OPENAI_API_KEY not found. Chat service will not work properly.")

        self.client = OpenAI(api_key=api_key) if api_key else None
        self.model = os.getenv("OPENAI_CHAT_MODEL", "gpt-3.5-turbo")

        if self.logger:
            self.logger.info("Chat Service initialized")

    async def get_response(self, message: str, session_id: str = "default") -> Dict:
        # Cache lookup
        if self.cache:
            cached = self.cache.get_cached_response(message)
            if cached:
                if self.analytics: self.analytics.track_event("chat_cache_hit", metadata={"session_id": session_id})
                if self.logger: self.logger.info("Cache hit for chat query")
                # Also append to conversation view
                if self.cache:
                    self.cache.append_conversation(session_id, {
                        "question": message,
                        "answer": cached.get("response", ""),
                        "sources": [s.get("filename") for s in cached.get("sources", [])],
                        "context_chunks": len(cached.get("sources", []))
                    })
                return cached

        if not self.client:
            return {"response": "OpenAI API key not configured. Please set OPENAI_API_KEY.", "sources": []}

        try:
            # Retrieve
            if self.logger: self.logger.info(f"RAG search for: {message[:100]}...")
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

            system_prompt = (
                "You are a helpful AI assistant answering strictly from the provided context.\n"
                "If the answer isn't in the context, say so clearly. Be concise and cite relevant parts."
            )
            user_prompt = f"Context:\n{context}\n\nQuestion: {message}\n\nAnswer from the context above."

            # LLM
            if self.logger: self.logger.info("Calling OpenAI...")
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

            # Cache save
            if self.cache: self.cache.cache_response(message, result)

            # Conversation history in Redis
            if self.cache:
                self.cache.append_conversation(session_id, {
                    "question": message,
                    "answer": ai_response,
                    "sources": [s["filename"] for s in source_info],
                    "context_chunks": len(relevant_chunks)
                })

            # Analytics
            if self.analytics: self.analytics.track_event("chat_answered", metadata={"session_id": session_id})

            return result

        except Exception as e:
            if self.logger: self.logger.error(f"Chat error: {e}")
            if self.analytics: self.analytics.track_event("chat_error", metadata={"error": str(e), "session_id": session_id})
            return {"response": f"Error processing your question: {e}", "sources": []}

    # Redis-backed history accessors
    def get_conversation_history(self, session_id: str) -> List[Dict]:
        if self.cache:
            return self.cache.get_conversation(session_id)
        return []

    def clear_conversation_history(self, session_id: str):
        if self.cache:
            self.cache.clear_conversation(session_id)

    def get_all_sessions(self) -> List[str]:
        # With Redis lists, you’d typically track sessions separately or scan keys.
        # For simplicity, omit listing all sessions here.
        return []
