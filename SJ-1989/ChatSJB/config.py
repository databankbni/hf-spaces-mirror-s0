import os
from dotenv import load_dotenv

load_dotenv()

NOTION_API_KEY = os.getenv('NOTION_API_KEY')
NOTION_PAGE_ID = os.getenv('NOTION_PAGE_ID')
CHUNKS_USED = int(os.getenv('CHUNKS_USED', 3))
USE_AI = os.getenv('USE_AI', 'false').lower() == 'true'
RETRIEVAL_METHOD = os.getenv('RETRIEVAL_METHOD', 'tfidf') # tfidf, dense_embeddings, hybrid
MODEL = os.getenv('MODEL', 'gemini-2.5-flash')
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
TFIDF_WEIGHT = float(os.getenv('TFIDF_WEIGHT', 0.3))
DENSE_EMBEDDINGS_WEIGHT = float(os.getenv('TFIDF_WEIGHT', 0.7))