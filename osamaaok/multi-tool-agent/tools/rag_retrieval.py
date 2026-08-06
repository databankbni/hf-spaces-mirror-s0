import os
import glob
from sentence_transformers import SentenceTransformer
import numpy as np
import faiss

EMBEDDING_MODEL = SentenceTransformer("all-MiniLM-L6-v2")

def embed_chunks(chunks):
    """
    Converts each chunk's text into an embedding vector.
    Returns a numpy array of shape (num_chunks, embedding_dimension).
    """
    texts = [chunk["text"] for chunk in chunks]
    embeddings = EMBEDDING_MODEL.encode(texts, show_progress_bar=True)
    return np.array(embeddings).astype("float32")

DOCS_FOLDER = "docs"

def load_and_chunk_documents(chunk_size=500, overlap=50):
    chunks = []
    docs_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "docs"))
    file_paths = glob.glob(os.path.join(docs_path, "*.md"))

    for path in file_paths:
        with open(path, "r", encoding="utf-8") as f:
            text = f.read()

        filename = os.path.basename(path)
        start = 0
        while start < len(text):
            end = start + chunk_size
            chunk_text = text[start:end]
            chunks.append({
                "text": chunk_text,
                "source": filename
            })
            start += chunk_size - overlap

    return chunks

# Build the index once, at import time, so it's ready to query immediately
_chunks = load_and_chunk_documents()
_embeddings = embed_chunks(_chunks)
_index = faiss.IndexFlatL2(_embeddings.shape[1])
_index.add(_embeddings)


def rag_retrieval(query, top_k=3):
    """
    Searches the knowledge base for the chunks most relevant to the query.
    Returns a combined text block of the top matching chunks, with sources.
    """
    query_embedding = EMBEDDING_MODEL.encode([query]).astype("float32")
    distances, indices = _index.search(query_embedding, top_k)

    results = []
    for rank, idx in enumerate(indices[0], start=1):
        chunk = _chunks[idx]
        results.append(f"[Match {rank}, from {chunk['source']}]\n{chunk['text']}")

    return "\n\n".join(results)

if __name__ == "__main__":
    result = rag_retrieval("What is the N times M integration problem MCP solves?")
    print(result)