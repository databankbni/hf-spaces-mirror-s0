"""
Sala AI - View Chroma DB Contents
Shows the actual text content stored in both the products and wiki vector stores.
"""

from dotenv import load_dotenv
load_dotenv()

from chatbot.rag import get_embeddings
from langchain_chroma import Chroma

embeddings = get_embeddings()

print("=" * 60)
print("PRODUCTS VECTOR DB (chroma_db/products)")
print("=" * 60)
product_store = Chroma(
    persist_directory="./chroma_db/products",
    embedding_function=embeddings,
)
count = product_store._collection.count()
print(f"Total products: {count}\n")

data = product_store._collection.get(limit=5)  # first 5 only
for i, doc in enumerate(data["documents"]):
    print(f"--- Product {i+1} ---")
    print(doc)
    print()

print("\n" + "=" * 60)
print("WIKI VECTOR DB (chroma_db/wiki)")
print("=" * 60)
wiki_store = Chroma(
    persist_directory="./chroma_db/wiki",
    embedding_function=embeddings,
)
count = wiki_store._collection.count()
print(f"Total wiki chunks: {count}\n")

data = wiki_store._collection.get(limit=10)  # show all if small
for i, doc in enumerate(data["documents"]):
    title = data["metadatas"][i].get("title", "N/A")
    print(f"--- Wiki chunk {i+1} (title: {title}) ---")
    print(doc)
    print()