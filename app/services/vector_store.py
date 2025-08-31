import os
import json
import uuid
from typing import List, Dict, Optional
from abc import ABC, abstractmethod
from app.core.config import settings
import numpy as np
from pinecone import Pinecone, ServerlessSpec
import google.generativeai as genai

# ---------- Base Interface ----------
class IVectorStore(ABC):
    @abstractmethod
    async def store_document(self, chunks: List[Dict], filename: str) -> str: ...
    
    @abstractmethod
    async def search(self, query: str, k: int = 5) -> List[Dict]: ...
    
    @abstractmethod
    async def list_documents(self) -> List[Dict]: ...
    
    @abstractmethod
    async def delete_document(self, doc_id: str): ...
    
    @abstractmethod
    def get_stats(self) -> Dict: ...

# ---------- Pinecone Backend (v3) with Gemini Embeddings ----------
class PineconeVectorStore(IVectorStore):
    def __init__(self):
        api_key = settings.PINECONE_API_KEY
        index_name = settings.PINECONE_INDEX
        cloud = settings.PINECONE_CLOUD or "aws"
        region = settings.PINECONE_REGION or "us-west-1"

        if not api_key:
            raise RuntimeError("Pinecone API key missing. Set PINECONE_API_KEY.")

        # Check for Gemini API key
        if not settings.GEMINI_API_KEY:
            raise RuntimeError("Gemini API key missing. Set GEMINI_API_KEY for embeddings.")

        self.pc = Pinecone(api_key=api_key)
        self.index_name = index_name
        
        # Configure Gemini client for embeddings
        genai.configure(api_key=settings.GEMINI_API_KEY)
        self.embedding_model = "gemini-embedding-001"
        self.dimension = 1024  # Using 1024 to match your Pinecone index

        # Create index if not exists with correct dimension
        if index_name not in [idx["name"] for idx in self.pc.list_indexes()]:
            self.pc.create_index(
                name=index_name,
                dimension=self.dimension,
                metric="cosine",
                spec=ServerlessSpec(cloud=cloud, region=region)
            )

        self.index = self.pc.Index(index_name)
        self.documents = {}
        self._load_documents()

    def _get_embeddings(self, texts: List[str]) -> np.ndarray:
        """Get embeddings using Gemini's embedding model"""
        embeddings = []
        
        try:
            # Process texts one by one (Gemini embedding has single input limitation)
            for text in texts:
                result = genai.embed_content(
                    model=self.embedding_model,
                    content=text,
                    output_dimensionality=self.dimension  # Specify output dimensions
                )
                embeddings.append(result['embedding'])
            
            return np.array(embeddings)
            
        except Exception as e:
            raise RuntimeError(f"Failed to get Gemini embeddings: {e}")

    async def store_document(self, chunks: List[Dict], filename: str) -> str:
        doc_id = str(uuid.uuid4())
        texts = [c["text"] for c in chunks]
        embs = self._get_embeddings(texts)
        
        # Normalize embeddings
        embs = embs / np.linalg.norm(embs, axis=1, keepdims=True)

        vectors = []
        for i, (emb, chunk) in enumerate(zip(embs, chunks)):
            vid = f"{doc_id}_{i}"
            vectors.append({
                "id": vid,
                "values": emb.tolist(),
                "metadata": {
                    "doc_id": doc_id,
                    "filename": filename,
                    "chunk_index": chunk.get("chunk_index", i),
                    "text": chunk["text"]
                }
            })

        self.index.upsert(vectors=vectors)
        self.documents[doc_id] = {
            "doc_id": doc_id,
            "filename": filename,
            "chunk_count": len(chunks)
        }
        self._save_documents()
        return doc_id

    async def search(self, query: str, k: int = 5) -> List[Dict]:
        q = self._get_embeddings([query])
        q = q / np.linalg.norm(q, axis=1, keepdims=True)
        res = self.index.query(vector=q[0].tolist(), top_k=k, include_metadata=True)

        results = []
        for match in getattr(res, "matches", []):
            md = match.metadata or {}
            results.append({
                "text": md.get("text", ""),
                "chunk_index": md.get("chunk_index", 0),
                "filename": md.get("filename", "Unknown"),
                "similarity_score": float(match.score),
                "doc_id": md.get("doc_id")
            })
        return results

    async def search_with_filter(self, query: str, k: int = 5, filter_dict: Optional[Dict] = None) -> List[Dict]:
        q = self._get_embeddings([query])
        q = q / np.linalg.norm(q, axis=1, keepdims=True)

        filter_expr = None
        if filter_dict:
            filter_expr = {k: {"$eq": v} for k, v in filter_dict.items()}

        res = self.index.query(
            vector=q[0].tolist(),
            top_k=k,
            include_metadata=True,
            filter=filter_expr
        )

        results = []
        for match in getattr(res, "matches", []):
            md = match.metadata or {}
            results.append({
                "text": md.get("text", ""),
                "chunk_index": md.get("chunk_index", 0),
                "filename": md.get("filename", "Unknown"),
                "similarity_score": float(match.score),
                "doc_id": md.get("doc_id")
            })
        return results

    async def list_documents(self) -> List[Dict]:
        return list(self.documents.values())

    async def delete_document(self, doc_id: str):
        try:
            self.index.delete(filter={"doc_id": {"$eq": doc_id}})
        except Exception:
            pass

        if doc_id in self.documents:
            del self.documents[doc_id]
            self._save_documents()

    def _docs_path(self):
        os.makedirs("data", exist_ok=True)
        return "data/pinecone_documents.json"

    def _save_documents(self):
        with open(self._docs_path(), "w") as f:
            json.dump(self.documents, f, indent=2)

    def _load_documents(self):
        try:
            with open(self._docs_path(), "r") as f:
                self.documents = json.load(f)
        except Exception:
            self.documents = {}

    def get_stats(self) -> Dict:
        stats = self.index.describe_index_stats()
        total = stats.total_vector_count if hasattr(stats, "total_vector_count") else 0
        return {
            "backend": "pinecone-v3",
            "embedding_model": self.embedding_model,
            "total_documents": len(self.documents),
            "index_size": int(total),
            "embedding_dimension": self.dimension
        }

# ---------- Factory ----------
def get_vector_store() -> IVectorStore:
    return PineconeVectorStore()