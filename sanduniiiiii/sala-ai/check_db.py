from dotenv import load_dotenv
load_dotenv()

from chatbot.rag import get_embeddings
from langchain_chroma import Chroma

embeddings = get_embeddings()
store = Chroma(
    persist_directory="./chroma_db/products",
    embedding_function=embeddings,
)

count = store._collection.count()
print(f"Total products in DB: {count}\n")

# Peek at first 5 entries
data = store._collection.get(limit=5)
for i, doc in enumerate(data["documents"]):
    print(f"--- Product {i+1} ---")
    print(doc)
    print()