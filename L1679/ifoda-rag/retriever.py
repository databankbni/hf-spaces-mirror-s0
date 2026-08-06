"""
Hybrid retrieval: dense + sparse (keyword) + cross-encoder reranking for maximum accuracy.
"""
import re
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass

import chromadb
from chromadb.utils import embedding_functions
from sentence_transformers import CrossEncoder

from config import *

# multilingual-e5-large-instruct REQUIRES an instruction prefix on QUERIES.
# Passages/documents stored in the index must stay WITHOUT a prefix.
# Skipping this hurts retrieval quality noticeably.
E5_QUERY_TASK = (
    "Given an agrochemical question, retrieve the relevant IFODA product, "
    "its dosage, target crop/pest and usage instructions"
)

def _is_e5_instruct(model_name: str) -> bool:
    name = (model_name or "").lower()
    return "e5" in name and "instruct" in name

@dataclass
class RetrievedChunk:
    id: str; text: str; score: float; metadata: Dict; source: str

class HybridRetriever:
    def __init__(self):
        self.client = chromadb.PersistentClient(path=VECTOR_DB_DIR)
        self.embedding_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
            model_name=EMBEDDING_MODEL, device="cpu")
        self.collection = self.client.get_collection(
            name=CHROMA_COLLECTION, embedding_function=self.embedding_fn)
        self.doc_count = self.collection.count()
        print(f"[RETRIEVAL] Collection '{CHROMA_COLLECTION}': {self.doc_count} docs")
        self._reranker = None

    @property
    def reranker(self):
        if self._reranker is None:
            print(f"[RETRIEVAL] Loading reranker: {RERANKER_MODEL}")
            try: self._reranker = CrossEncoder(RERANKER_MODEL, device="cpu")
            except: self._reranker = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2", device="cpu")
        return self._reranker

    def _embed_query(self, query: str):
        """Embed a query, applying the e5-instruct prefix when required.
        Reuses the already-loaded embedding model (no extra model load)."""
        text = query
        if _is_e5_instruct(EMBEDDING_MODEL):
            text = f"Instruct: {E5_QUERY_TASK}\nQuery: {query}"
        return self.embedding_fn([text])[0]

    def dense_search(self, query: str, top_k: int = TOP_K_RETRIEVE, where: Optional[Dict] = None) -> List[RetrievedChunk]:
        res = self.collection.query(query_embeddings=[self._embed_query(query)], n_results=top_k, where=where,
                                     include=["documents","metadatas","distances"])
        chunks = []
        for i in range(len(res["ids"][0])):
            dist = res["distances"][0][i]
            score = 1.0 - (dist / 2.0)
            meta = res["metadatas"][0][i] or {}
            chunks.append(RetrievedChunk(id=res["ids"][0][i], text=res["documents"][0][i] or "",
                           score=score, metadata=meta, source=meta.get("source","unknown")))
        return chunks

    def sparse_search(self, query: str, top_k: int = TOP_K_RETRIEVE) -> List[RetrievedChunk]:
        all_docs = self.collection.get(include=["documents","metadatas"])
        if not all_docs["ids"]: return []
        query_words = set(re.findall(r'[a-zA-Zа-яА-ЯёЁ0-9]+', query.lower()))
        if not query_words: return []
        scored = []
        for i, did in enumerate(all_docs["ids"]):
            text = (all_docs["documents"][i] or "").lower()
            if not text: continue
            score = sum(len(re.findall(re.escape(w), text)) * (1.0/max(1,len(w))) for w in query_words)
            if score > 0: scored.append((score, i))
        scored.sort(key=lambda x: x[0], reverse=True)
        top = scored[:top_k]
        max_s = top[0][0] if top else 1
        chunks = []
        for s, idx in top:
            meta = all_docs["metadatas"][idx] or {}
            chunks.append(RetrievedChunk(id=all_docs["ids"][idx], text=all_docs["documents"][idx] or "",
                           score=s/max_s, metadata=meta, source=meta.get("source","unknown")))
        return chunks

    def _rrf(self, result_lists: List[List[RetrievedChunk]], k: float = 60.0) -> List[RetrievedChunk]:
        fused = {}
        for results in result_lists:
            for rank, chunk in enumerate(results):
                if chunk.id not in fused: fused[chunk.id] = {"chunk": chunk, "score": 0.0}
                fused[chunk.id]["score"] += 1.0/(k+rank+1)
        sorted_items = sorted(fused.values(), key=lambda x: x["score"], reverse=True)
        for item in sorted_items: item["chunk"].score = item["score"]
        return [item["chunk"] for item in sorted_items]

    def hybrid_search(self, query: str, top_k: int = TOP_K_RETRIEVE, filters=None) -> List[RetrievedChunk]:
        dense = self.dense_search(query, top_k, filters)
        sparse = self.sparse_search(query, top_k)
        fused = self._rrf([dense, sparse])
        return fused[:top_k]

    def rerank(self, query: str, candidates: List[RetrievedChunk], top_k: int = TOP_K_RERANK) -> List[RetrievedChunk]:
        if not candidates: return []
        pairs = [(query, c.text[:2000]) for c in candidates]
        scores = self.reranker.predict(pairs)
        for i, s in enumerate(scores): candidates[i].score = float(s)
        candidates.sort(key=lambda x: x.score, reverse=True)
        return candidates[:top_k]

    def retrieve(self, query: str, top_k: int = TOP_K_RERANK, use_rerank: bool = True) -> List[RetrievedChunk]:
        candidates = self.hybrid_search(query, top_k=TOP_K_RETRIEVE)
        if not candidates: return []
        return self.rerank(query, candidates, top_k) if use_rerank else candidates[:top_k]

    def get_context_for_llm(self, results: List[RetrievedChunk], max_tokens: int = 3000) -> str:
        parts = []
        for i, r in enumerate(results):
            src = r.metadata.get("source","?"); prod = r.metadata.get("product_name","N/A")
            parts.append(f"SOURCE {i+1} [{src} | Product: {prod}]:\n{r.text}")
        ctx = "\n\n---\n\n".join(parts)
        if len(ctx) > max_tokens*4: ctx = ctx[:max_tokens*4] + "\n...[truncated]"
        return ctx

    def format_results(self, results: List[RetrievedChunk]) -> str:
        if not results: return "No relevant documents found."
        out = []
        for i, r in enumerate(results):
            src = r.metadata.get("source","?"); prod = r.metadata.get("product_name","N/A")
            dtype = r.metadata.get("doc_type","N/A")
            out.append(f"[Doc {i+1}] Score: {r.score:.4f}\n  Source: {src}\n  Product: {prod}\n  Type: {dtype}\n  Content: {r.text[:500]}")
        return "\n\n".join(out)

if __name__ == "__main__":
    ret = HybridRetriever()
    for q in ["Какой инсектицид против тли на хлопчатнике?", "What fungicide for powdery mildew on wheat?"]:
        print(f"\n{'='*60}\nQUERY: {q}\n{'='*60}")
        print(ret.format_results(ret.retrieve(q, top_k=3)))
