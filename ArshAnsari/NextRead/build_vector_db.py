import pandas as pd
from langchain_core.documents import Document
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_chroma import Chroma
import os

def build_database():
    print("Loading data from books_with_emotions.csv...")
    # Read the dataset
    books = pd.read_csv("books_with_emotions.csv")
    
    print(f"Loaded {len(books)} books. Preparing documents...")
    documents = []
    
    for _, row in books.iterrows():
        # Ensure we have a valid tagged_description
        page_content = str(row.get("tagged_description", "")).strip()
        if not page_content or page_content == "nan":
            continue
            
        # Upgrade 02: Injecting metadata directly into LangChain Document objects
        metadata = {
            "isbn13": int(row["isbn13"]),
            "title": str(row["title"]),
            "category": str(row.get("simple_categories", "Unknown")),
            "joy": float(row.get("joy", 0.0)),
            "sadness": float(row.get("sadness", 0.0)),
            "fear": float(row.get("fear", 0.0)),
            "anger": float(row.get("anger", 0.0)),
            "surprise": float(row.get("surprise", 0.0))
        }
        
        doc = Document(page_content=page_content, metadata=metadata)
        documents.append(doc)

    print("Initializing Hugging Face Embeddings (all-MiniLM-L6-v2)...")
    embeddings = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")
    
    persist_directory = "chroma_db"
    if os.path.exists(persist_directory):
        print(f"Warning: {persist_directory} already exists. We will overwrite/add to it.")

    print(f"Generating embeddings and saving to {persist_directory}...")
    print("This might take a few minutes. Please wait...")
    
    # Upgrade 01: Generating the Chroma DB persistently
    db = Chroma.from_documents(
        documents,
        embedding=embeddings,
        persist_directory=persist_directory
    )
    
    print(f"Success! Vector database successfully persisted to '{persist_directory}' directory.")

if __name__ == "__main__":
    build_database()
