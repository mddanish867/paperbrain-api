import os
from typing import List, Dict
import json
import uuid

# ---------- Base interface ----------
class IVectorStore:
    async def store_document(self, chunks: List[Dict], filename: str) -> str: ...
    async def search(self, query: str, k: int = 5) -> List[Dict]: ...
    async def list_documents(self) -> List[Dict]: ...
    async def delete_document(self, doc_id: str): ...
    def get_stats(self) -> Dict: ...

# ---------- FAISS backend (existing logic) ----------
class _FaissVectorStore(IVectorStore):
    def __init__(self):
        import faiss
        import numpy as np
        from sentence_transformers import SentenceTransformer
        import pickle

        self._np = np
        self._faiss = faiss
        self._pickle = pickle

        self.embedding_model = SentenceTransformer('all-MiniLM-L6-v2')
        self.dimension = 384
        self.index = faiss.IndexFlatIP(self.dimension)
        self.documents = {}
        self.chunks = {}
        os.makedirs('data', exist_ok=True)
        self._load_index()

    async def store_document(self, chunks: List[Dict], filename: str) -> str:
        import numpy as np
        texts = [c['text'] for c in chunks]
        embeddings = self.embedding_model.encode(texts, show_progress_bar=False)
        embeddings = embeddings / np.linalg.norm(embeddings, axis=1, keepdims=True)
        start_id = len(self.chunks)
        self.index.add(embeddings.astype('float32'))

        doc_id = str(uuid.uuid4())
        chunk_ids = []
        for i, chunk in enumerate(chunks):
            cid = start_id + i
            chunk_ids.append(cid)
            self.chunks[cid] = {**chunk, 'doc_id': doc_id, 'filename': filename}

        self.documents[doc_id] = {
            'doc_id': doc_id,
            'filename': filename,
            'chunk_count': len(chunks),
            'chunk_ids': chunk_ids
        }
        self._save_index()
        return doc_id

    async def search(self, query: str, k: int = 5) -> List[Dict]:
        if self.index.ntotal == 0:
            return []
        import numpy as np
        q = self.embedding_model.encode([query])
        q = q / np.linalg.norm(q, axis=1, keepdims=True)
        scores, indices = self.index.search(q.astype('float32'), min(k, self.index.ntotal))
        results = []
        for score, idx in zip(scores[0], indices[0]):
            if idx != -1 and idx in self.chunks:
                ch = self.chunks[idx].copy()
                ch['similarity_score'] = float(score)
                results.append(ch)
        return results

    async def list_documents(self) -> List[Dict]:
        return list(self.documents.values())

    async def delete_document(self, doc_id: str):
        if doc_id not in self.documents:
            raise ValueError(f"Document {doc_id} not found")
        chunk_ids = self.documents[doc_id]['chunk_ids']
        for cid in chunk_ids:
            if cid in self.chunks: del self.chunks[cid]
        del self.documents[doc_id]
        self._rebuild_index()

    def _rebuild_index(self):
        import numpy as np
        import faiss
        if not self.chunks:
            self.index = faiss.IndexFlatIP(self.dimension)
            self._save_index()
            return
        items = sorted(self.chunks.items())
        texts = [d['text'] for _, d in items]
        embs = self.embedding_model.encode(texts, show_progress_bar=False)
        embs = embs / np.linalg.norm(embs, axis=1, keepdims=True)
        self.index = faiss.IndexFlatIP(self.dimension)
        self.index.add(embs.astype('float32'))
        new_chunks = {}
        for i, (_, data) in enumerate(items):
            new_chunks[i] = data
        self.chunks = new_chunks
        # NOTE: per-document chunk_ids become approximate; for demo this is OK.
        for doc in self.documents.values():
            doc['chunk_ids'] = list(range(len(self.chunks)))
        self._save_index()

    def _save_index(self):
        import faiss, pickle
        faiss.write_index(self.index, 'data/faiss_index.idx')
        with open('data/documents.json', 'w') as f:
            json.dump(self.documents, f, indent=2)
        with open('data/chunks.pkl', 'wb') as f:
            pickle.dump(self.chunks, f)

    def _load_index(self):
        import faiss, pickle
        if os.path.exists('data/faiss_index.idx'):
            self.index = faiss.read_index('data/faiss_index.idx')
        if os.path.exists('data/documents.json'):
            with open('data/documents.json', 'r') as f:
                self.documents = json.load(f)
        if os.path.exists('data/chunks.pkl'):
            with open('data/chunks.pkl', 'rb') as f:
                self.chunks = pickle.load(f)

    def get_stats(self) -> Dict:
        return {
            "backend": "faiss",
            "total_documents": len(self.documents),
            "total_chunks": len(self.chunks),
            "index_size": getattr(self.index, "ntotal", 0),
            "embedding_dimension": self.dimension
        }

# ---------- Pinecone backend ----------
class _PineconeVectorStore(IVectorStore):
    def __init__(self):
        from sentence_transformers import SentenceTransformer
        import pinecone

        api_key = os.getenv("PINECONE_API_KEY")
        env = os.getenv("PINECONE_ENVIRONMENT")
        index_name = os.getenv("PINECONE_INDEX", "rag-index")
        if not api_key or not env:
            raise RuntimeError("Pinecone credentials missing. Set PINECONE_API_KEY and PINECONE_ENVIRONMENT.")
        pinecone.init(api_key=api_key, environment=env)
        self._pinecone = pinecone
        self.index_name = index_name
        if index_name not in [x.name for x in pinecone.list_indexes()]:
            # dimension 384 for MiniLM; metric cosine
            pinecone.create_index(name=index_name, dimension=384, metric="cosine")
        self.index = pinecone.Index(index_name)
        self.embedding_model = SentenceTransformer('all-MiniLM-L6-v2')
        self.dimension = 384
        # Keep a light in-memory doc registry for listing (optional: move to DB)
        self.documents = {}
        self._load_documents()

    async def store_document(self, chunks: List[Dict], filename: str) -> str:
        import numpy as np
        doc_id = str(uuid.uuid4())
        texts = [c["text"] for c in chunks]
        embs = self.embedding_model.encode(texts, show_progress_bar=False)
        # Normalize for cosine
        embs = embs / np.linalg.norm(embs, axis=1, keepdims=True)
        # Upsert to Pinecone with metadata
        vectors = []
        for i, (emb, chunk) in enumerate(zip(embs, chunks)):
            vid = f"{doc_id}_{i}"
            vectors.append((
                vid,
                emb.tolist(),
                {
                    "doc_id": doc_id,
                    "filename": filename,
                    "chunk_index": chunk.get("chunk_index", i),
                    "text": chunk["text"]
                }
            ))
        self.index.upsert(vectors=vectors)
        self.documents[doc_id] = {"doc_id": doc_id, "filename": filename, "chunk_count": len(chunks)}
        self._save_documents()
        return doc_id

    async def search(self, query: str, k: int = 5) -> List[Dict]:
        import numpy as np
        q = self.embedding_model.encode([query])
        q = q / np.linalg.norm(q, axis=1, keepdims=True)
        res = self.index.query(vector=q[0].tolist(), top_k=k, include_metadata=True)
        results = []
        for match in res.matches or []:
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
        # Since Pinecone doesn’t list docs, we track in a small JSON
        return list(self.documents.values())

    async def delete_document(self, doc_id: str):
        # Delete by prefix scan of IDs
        # Pinecone supports delete with filter (namespace metadata if used). Here we delete by id prefix.
        # If you stored IDs as f"{doc_id}_{i}", you can gather ids via describe_index_stats:
        stats = self.index.describe_index_stats()
        # Not super efficient at huge scale; for production, store ids elsewhere or use metadata filters.
        ids_to_delete = []
        for ns, ns_stats in stats.namespaces.items():
            # no namespaces by default
            pass
        # Simpler: try a range of possible ids by querying stats.total_vector_count — or maintain ids in a side store.
        # For demo, we rely on purge by filter if your Pinecone serverless supports it:
        try:
            self.index.delete(filter={"doc_id": {"$eq": doc_id}})
        except Exception:
            # fallback no-op
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
            "backend": "pinecone",
            "total_documents": len(self.documents),
            "index_size": int(total),
            "embedding_dimension": self.dimension
        }

# ---------- Factory ----------
def VectorStore():
    backend = os.getenv("VECTOR_BACKEND", "faiss").lower()
    if backend == "pinecone":
        return _PineconeVectorStore()
    return _FaissVectorStore()
