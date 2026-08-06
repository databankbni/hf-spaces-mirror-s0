---
project_name: legal_RAG_system
github_url: https://github.com/neural-arun/legal_RAG_system
language: Python
stars: 0
topics: 
updated_at: 2026-04-04T19:38:26Z
---

# legal_RAG_system

> **GitHub Repository:** [https://github.com/neural-arun/legal_RAG_system](https://github.com/neural-arun/legal_RAG_system)  
> **Primary Language:** Python | **Stars:** 0 | **Forks:** 0  
> **Description:** No description provided.

---

# Legal RAG System

A legal Retrieval-Augmented Generation (RAG) pipeline built for Indian legal documents.

This project processes legal PDFs, chunks them using document-specific strategies, stores embeddings in ChromaDB, retrieves relevant chunks for a query, and answers questions using a Groq-hosted LLM.

## What This Project Does

- Creates a manifest for all legal PDFs in `docs/`
- Extracts raw text page by page
- Cleans and structures each document before chunking
- Chunks legal material by its real structure:
  - IPC by section
  - Constitution by article
  - Judgments by paragraph blocks
- Validates chunk quality before embedding
- Stores vectors in ChromaDB
- Retrieves relevant legal chunks using exact reference + semantic search
- Generates final answers using `llama-3.3-70b-versatile` on Groq

## Current Corpus

The pipeline is designed around these documents:

- `IPC.pdf`
- `constitution.pdf`
- `case_1.PDF`
- `case_2.PDF`

These files are intentionally ignored by Git and should be placed inside the `docs/` folder locally.

## Project Structure

```text
01_document_manifest.py
02_extract_text.py
03_clean_and_structure.py
04_chunk_documents.py
05_validate_chunks.py
06_embed_and_index.py
07_query.py
08_answer.py
requirements.txt
docs/
db/
output/
```

## Pipeline

### `01_document_manifest.py`

Scans `docs/`, identifies PDFs, and creates `manifest.json`.

### `02_extract_text.py`

Extracts page-level text from each enabled PDF using `pypdf`.

### `03_clean_and_structure.py`

Removes front matter, headers, and noisy pages. Detects the real body of each legal document.

### `04_chunk_documents.py`

Chunks each document using a strategy based on document type:

- statutes by section
- constitution by article
- judgments by paragraph blocks

Outputs clean chunks to `output/chunks.json`.

### `05_validate_chunks.py`

Validates chunk IDs, metadata, page ranges, and suspicious chunk quality issues.

### `06_embed_and_index.py`

Embeds chunks with OpenAI `text-embedding-3-small` and stores them in ChromaDB under `db/`.

### `07_query.py`

Retrieves chunks for a legal query using:

- exact reference matching for things like `Section 302 IPC` or `Article 21`
- semantic retrieval from ChromaDB
- lexical fallback if Chroma is unavailable

### `08_answer.py`

Builds the final answer layer on top of retrieval using Groq `llama-3.3-70b-versatile`.

The CLI is kept simple:

- prints only a clean question block
- prints only the final answer block
- if the answer is not found, it replies:
  - `I do not have information regarding this.`

## Setup

### 1. Create a virtual environment

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```

### 2. Install dependencies

```powershell
pip install -r requirements.txt
```

### 3. Add environment variables

Create a `.env` file with:

```env
OPENAI_API_KEY=your_openai_key
GROQ_API_KEY=your_groq_key
```

`OPENAI_API_KEY` is used for embeddings and query-time semantic retrieval.

`GROQ_API_KEY` is used for final answer generation.

## How To Run

### Step 1: Build the manifest

```powershell
.\venv\Scripts\python.exe 01_document_manifest.py
```

### Step 2: Extract text

```powershell
.\venv\Scripts\python.exe 02_extract_text.py
```

### Step 3: Clean and structure documents

```powershell
.\venv\Scripts\python.exe 03_clean_and_structure.py
```

### Step 4: Chunk documents

```powershell
.\venv\Scripts\python.exe 04_chunk_documents.py
```

### Step 5: Validate chunks

```powershell
.\venv\Scripts\python.exe 05_validate_chunks.py
```

### Step 6: Embed and index

```powershell
.\venv\Scripts\python.exe 06_embed_and_index.py
```

### Step 7: Query retrieval

```powershell
.\venv\Scripts\python.exe 07_query.py
```

Single query mode:

```powershell
.\venv\Scripts\python.exe 07_query.py --query "What is Section 378 IPC?"
```

Run retrieval evaluation:

```powershell
.\venv\Scripts\python.exe 07_query.py --eval
```

### Step 8: Generate answers

```powershell
.\venv\Scripts\python.exe 08_answer.py
```

Single question mode:

```powershell
.\venv\Scripts\python.exe 08_answer.py --query "What is Article 21 of the Constitution?"
```

## Example Questions

- `What is Section 378 IPC?`
- `What is Section 302 IPC?`
- `What is Article 21 of the Constitution?`
- `Which article guarantees freedom of speech?`
- `What did Hira Lal Chaudhary vs State say about jurisdiction in criminal breach of trust cases?`
- `What is the relationship between Section 378 IPC and the Neerja Singh case discussion?`

## Notes

- `docs/`, `db/`, `output/`, `.env`, and local temp folders are excluded from Git.
- The retrieval pipeline is strongest for direct section/article lookup and grounded case-based questions.
- The answer layer is configured to avoid hallucinated answers and to return a strict fallback when information is missing.

## Tech Stack

- Python
- PyPDF
- LangChain
- OpenAI Embeddings
- ChromaDB
- Groq

## Future Improvements

- Add hybrid BM25 + vector retrieval
- Add reranking for retrieved chunks
- Add more judgments and evaluation queries
- Add a simple web UI for legal Q&A
