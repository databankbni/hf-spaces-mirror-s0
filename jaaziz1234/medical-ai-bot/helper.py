# src/helper.py
# ---------------------------------------------------------------
# Helper utilities for the End-to-End Medical Chatbot project.
# Modernized for LangChain >= 0.2 / 1.x  (2024+)
# ---------------------------------------------------------------

from __future__ import annotations

import os
from typing import List

from langchain_google_genai import ChatGoogleGenerativeAI

# Document loaders → langchain_community
from langchain_community.document_loaders import DirectoryLoader, PyPDFLoader

# Text splitter → dedicated langchain_text_splitters package
from langchain_text_splitters import RecursiveCharacterTextSplitter

# Embeddings → dedicated langchain_huggingface package
from langchain_huggingface import HuggingFaceEmbeddings


# ── Load ────────────────────────────────────────────────────────
def load_pdf_file(data: str) -> List:
    """
    Recursively load every ``*.pdf`` inside *data* directory and
    return a flat list of LangChain ``Document`` objects.

    Parameters
    ----------
    data : str
        Path to the folder that contains your PDF source files.

    Returns
    -------
    List[Document]
    """
    loader = DirectoryLoader(
        data,
        glob="*.pdf",
        loader_cls=PyPDFLoader,
    )
    return loader.load()


# ── Split ───────────────────────────────────────────────────────
def text_split(extracted_data: List) -> List:
    """
    Split a list of ``Document`` objects into smaller, overlapping
    text chunks suitable for embedding.

    Parameters
    ----------
    extracted_data : List[Document]
        Documents produced by :func:`load_pdf_file`.

    Returns
    -------
    List[Document]
        Chunked documents (chunk_size=500, chunk_overlap=20).
    """
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=500,
        chunk_overlap=20,
    )
    return splitter.split_documents(extracted_data)


# ── Embed ───────────────────────────────────────────────────────
def download_hugging_face_embeddings() -> HuggingFaceEmbeddings:
    """
    Instantiate the HuggingFace sentence-transformer embedding model.

    Model  : sentence-transformers/all-MiniLM-L6-v2
    Output : 384-dimensional dense vectors

    Returns
    -------
    HuggingFaceEmbeddings
    """
    return HuggingFaceEmbeddings(
        model_name="sentence-transformers/all-MiniLM-L6-v2"
    )


# ── LLM ─────────────────────────────────────────────────────────
def load_gemini_llm(api_key: str):
    """
    Load the Gemini LLM securely by scrubbing conflicting environment variables.
    """
    # Scrub conflicting legacy environment variables to prevent router collisions
    os.environ.pop("GOOGLE_API_KEY", None)
    os.environ.pop("GEMINI_API_KEY", None)
    
    # Initialize the modern Gemini namespace explicitly passing the strict v1/v1beta compatible model
    llm = ChatGoogleGenerativeAI(
        model="gemini-2.5-flash",
        google_api_key=api_key.strip(),
        temperature=0.4,
        max_tokens=500
    )
    return llm