import json
import hashlib
from datetime import datetime
from typing import Dict, Optional
from app.core.config import settings
from app.services.vector_store import get_vector_store
from app.services.redis import redis_client
from app.utils.logger import logger

class SummaryService:
    def __init__(self, vector_store=None):
        self.vector_store = vector_store or get_vector_store()

        if not settings.GEMINI_API_KEY:
            logger.warning("GEMINI_API_KEY not found. Summary service will not work properly.")
            self.client = None
        else:
            try:
                import google.generativeai as genai
                genai.configure(api_key=settings.GEMINI_API_KEY)
                self.client = genai.GenerativeModel(settings.GEMINI_MODEL)
                logger.info(f"Initialized Gemini client for summary with model: {settings.GEMINI_MODEL}")
            except Exception as e:
                logger.error(f"Error initializing Gemini client: {e}")
                self.client = None

        self.model_name = settings.GEMINI_MODEL
        self.temperature = 0.5   # lower temperature for more factual summaries
        self.max_tokens = 2048

    async def generate_summary(self, doc_id: str, session_id: str = "default") -> Dict:
        if not self.client:
            return {"summary": "Gemini API not configured.", "sources": []}

        try:
            # Fetch relevant chunks from vector store
            relevant_chunks = await self.vector_store.search_with_filter(
                query="Summarize this document",
                k=15,
                filter_dict={"doc_id": doc_id}
            )

            if not relevant_chunks:
                return {"summary": f"No content found for doc_id: {doc_id}", "sources": []}

            # Prepare context
            context_pieces, source_info = [], []
            for i, chunk in enumerate(relevant_chunks):
                context_pieces.append(f"Section {i+1}: {chunk['text']}")
                source_info.append({
                    "filename": chunk.get('filename', 'Unknown'),
                    "chunk_index": chunk.get('chunk_index', 0),
                    "similarity_score": float(chunk.get('similarity_score', 0.0))
                })
            context = "\n\n".join(context_pieces)

            # Prompt for detailed summary
            prompt = f"""
You are an expert technical writer. Write a **comprehensive and detailed summary** 
of the following document. Your summary should include:

- High-level overview of the project/document
- Key objectives and goals
- Important details and insights
- Any challenges, limitations, or assumptions
- Potential applications or implications

Make the summary structured, clear, and detailed.

Context:
{context}

Now write the detailed summary:
"""

            generation_config = {"temperature": self.temperature, "max_output_tokens": self.max_tokens}
            response = self.client.generate_content(prompt, generation_config=generation_config)
            ai_summary = response.text.strip() if response.text else "I couldn't generate a summary."

            result = {"summary": ai_summary, "sources": source_info}

            # Cache summary (optional)
            cache_key = f"summary:{hashlib.md5(doc_id.encode()).hexdigest()}"
            try:
                redis_client.setex(cache_key, 24*3600, json.dumps(result))
            except Exception as e:
                logger.warning(f"Summary cache storage error: {e}")

            return result

        except Exception as e:
            logger.error(f"Summary error: {e}")
            return {"summary": f"Error generating summary: {e}", "sources": []}

summary_service = SummaryService()
