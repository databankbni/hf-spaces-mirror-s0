# store_index.py
# ---------------------------------------------------------------
# One-time script: load PDFs → chunk → embed → upsert to Pinecone.
# Run this ONCE before starting the Flask app.
# Modernized for LangChain >= 0.2 / 1.x  (2024+)
# ---------------------------------------------------------------

from __future__ import annotations

import os
import time

from dotenv import load_dotenv
from pinecone import Pinecone, ServerlessSpec
from langchain_pinecone import PineconeVectorStore

from src.helper import (
    download_hugging_face_embeddings,
    load_pdf_file,
    text_split,
)

# ── Environment ──────────────────────────────────────────────────
load_dotenv()

PINECONE_API_KEY = os.environ.get("PINECONE_API_KEY")
if not PINECONE_API_KEY:
    raise EnvironmentError("PINECONE_API_KEY is not set in your .env file.")

os.environ["PINECONE_API_KEY"] = PINECONE_API_KEY

# ── Load & chunk documents ───────────────────────────────────────
print("📄 Loading PDF files from Data/ ...")
extracted_data = load_pdf_file(data="Data/")
print(f"   Loaded {len(extracted_data)} page(s).")

print("✂️  Splitting into text chunks ...")
text_chunks = text_split(extracted_data)
print(f"   Created {len(text_chunks)} chunk(s).")

# ── Embeddings ───────────────────────────────────────────────────
print("🤗 Loading HuggingFace embedding model ...")
embeddings = download_hugging_face_embeddings()

# ── Pinecone index ───────────────────────────────────────────────
pc         = Pinecone(api_key=PINECONE_API_KEY)
INDEX_NAME = "medicalbot"

existing_indexes = [idx.name for idx in pc.list_indexes()]

if INDEX_NAME not in existing_indexes:
    print(f"🌲 Creating Pinecone index '{INDEX_NAME}' ...")
    pc.create_index(
        name=INDEX_NAME,
        dimension=384,        # all-MiniLM-L6-v2 produces 384-dim vectors
        metric="cosine",
        spec=ServerlessSpec(
            cloud="aws",
            region="us-east-1",
        ),
    )
    # Wait until the index is ready before upserting
    while not pc.describe_index(INDEX_NAME).status["ready"]:
        print("   Waiting for index to become ready ...")
        time.sleep(2)
    print("   Index is ready.")
else:
    print(f"✅ Pinecone index '{INDEX_NAME}' already exists – skipping creation.")

# ── Upsert embeddings ────────────────────────────────────────────
print("⬆️  Upserting document embeddings into Pinecone ...")
docsearch = PineconeVectorStore.from_documents(
    documents=text_chunks,
    index_name=INDEX_NAME,
    embedding=embeddings,
)

print("🎉 Done! Your Pinecone index is populated and ready for querying.")
