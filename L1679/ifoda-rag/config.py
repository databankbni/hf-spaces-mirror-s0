"""
RAG System Configuration for IFODA Agro Chemical Company
Максимальная точность — critical для агрохимии (неправильная дозировка = гибель урожая)
"""
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(os.path.dirname(BASE_DIR))
VECTOR_DB_DIR = os.path.join(BASE_DIR, "chroma_db")

# Multilingual embedding model (RU, EN, UZ)
EMBEDDING_MODEL = "intfloat/multilingual-e5-large-instruct"

# Multilingual cross-encoder reranker for precision
RERANKER_MODEL = "BAAI/bge-reranker-v2-m3"

# Chunking parameters
CHUNK_SIZE = 800
CHUNK_OVERLAP = 100

# Retrieval parameters
TOP_K_RETRIEVE = 20
TOP_K_RERANK = 5
BM25_WEIGHT = 0.3

# ChromaDB
CHROMA_COLLECTION = "ifoda_products"

SUPPORTED_LANGUAGES = ["ru", "en", "uz"]
