"""
Real data ingestion for the Generative Design Assistant.

Crawls research papers from:
1. arXiv API — academic papers on generative design, topology optimisation,
               lightweight automotive structures, additive manufacturing
2. Semantic Scholar API — additional papers with citation data and abstracts

Papers are deduplicated, chunked, embedded, and stored in ChromaDB.

Usage:
    python src/data/ingest_papers.py
    python src/data/ingest_papers.py --max 50
"""

import os
import re
import sys
import json
import time
import argparse
import xml.etree.ElementTree as ET
from pathlib import Path
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

import requests
import yaml
from loguru import logger
from sentence_transformers import SentenceTransformer
import chromadb
from chromadb.config import Settings


def load_config(path="configs/config.yaml"):
    with open(path) as f:
        raw = f.read()
    raw = re.sub(r'\$\{(\w+)\}', lambda m: os.environ.get(m.group(1), ""), raw)
    return yaml.safe_load(raw)


# ── arXiv queries ──────────────────────────────────────────────────────────
ARXIV_QUERIES = [
    "generative design topology optimization automotive",
    "lightweight structure design machine learning automotive",
    "additive manufacturing design optimization aerospace automotive",
    "multi-material design automotive lightweighting",
    "structural optimization neural network generative",
    "carbon fibre composite design automotive manufacturing",
    "aluminium alloy forming automotive body structure",
    "finite element analysis machine learning surrogate model",
]

# ── Semantic Scholar queries ───────────────────────────────────────────────
SEMANTIC_SCHOLAR_QUERIES = [
    "generative design engineering optimization",
    "topology optimization deep learning",
    "automotive lightweighting material selection",
    "additive manufacturing design for manufacturing",
    "structural design AI machine learning",
]


def fetch_arxiv(query: str, max_results: int = 30) -> list:
    """Fetch papers from arXiv API."""
    url = "http://export.arxiv.org/api/query"
    params = {
        "search_query": f"all:{query}",
        "start": 0,
        "max_results": max_results,
        "sortBy": "relevance",
        "sortOrder": "descending",
    }
    try:
        response = requests.get(url, params=params, timeout=30)
        response.raise_for_status()
    except Exception as e:
        logger.warning(f"arXiv fetch failed for '{query}': {e}")
        return []

    ns = {"atom": "http://www.w3.org/2005/Atom"}
    root    = ET.fromstring(response.text)
    entries = root.findall("atom:entry", ns)

    papers = []
    for entry in entries:
        try:
            arxiv_id  = entry.find("atom:id", ns).text.split("/abs/")[-1]
            title     = entry.find("atom:title", ns).text.strip().replace("\n", " ")
            abstract  = entry.find("atom:summary", ns).text.strip().replace("\n", " ")
            published = entry.find("atom:published", ns).text[:10]
            authors   = [a.find("atom:name", ns).text for a in entry.findall("atom:author", ns)]
            categories = [c.get("term") for c in entry.findall("atom:category", ns)]
            pdf_link  = next(
                (link.get("href") for link in entry.findall("atom:link", ns) if link.get("title") == "pdf"),
                f"https://arxiv.org/pdf/{arxiv_id}"
            )
            papers.append({
                "id":         f"arxiv_{arxiv_id}",
                "source":     "arxiv",
                "arxiv_id":   arxiv_id,
                "title":      title,
                "abstract":   abstract,
                "authors":    authors[:3],
                "published":  published,
                "categories": categories[:3],
                "url":        f"https://arxiv.org/abs/{arxiv_id}",
                "pdf_url":    pdf_link,
                "query":      query,
            })
        except Exception:
            continue

    return papers


def fetch_semantic_scholar(query: str, max_results: int = 20) -> list:
    """Fetch papers from Semantic Scholar API (no auth required)."""
    url = "https://api.semanticscholar.org/graph/v1/paper/search"
    params = {
        "query":  query,
        "limit":  max_results,
        "fields": "title,abstract,authors,year,externalIds,url,fieldsOfStudy",
    }
    headers = {"User-Agent": "GenerativeDesignAssistant/1.0 (academic research)"}

    try:
        response = requests.get(url, params=params, headers=headers, timeout=30)
        response.raise_for_status()
        data = response.json()
    except Exception as e:
        logger.warning(f"Semantic Scholar fetch failed for '{query}': {e}")
        return []

    papers = []
    for paper in data.get("data", []):
        abstract = paper.get("abstract", "")
        if not abstract or len(abstract) < 50:
            continue

        s2_id   = paper.get("paperId", "")
        ext_ids = paper.get("externalIds", {})
        arxiv_id = ext_ids.get("ArXiv", "")

        papers.append({
            "id":        f"s2_{s2_id}",
            "source":    "semantic_scholar",
            "s2_id":     s2_id,
            "arxiv_id":  arxiv_id,
            "title":     paper.get("title", ""),
            "abstract":  abstract,
            "authors":   [a.get("name", "") for a in paper.get("authors", [])[:3]],
            "published": str(paper.get("year", "")),
            "categories": (paper.get("fieldsOfStudy") or [])[:3],
            "url":        paper.get("url", f"https://www.semanticscholar.org/paper/{s2_id}"),
            "pdf_url":    f"https://arxiv.org/pdf/{arxiv_id}" if arxiv_id else "",
            "query":      query,
        })

    return papers


def deduplicate(papers: list) -> list:
    """Deduplicate by title similarity and arxiv_id."""
    seen_ids    = set()
    seen_titles = set()
    unique      = []

    for p in papers:
        arxiv_id    = p.get("arxiv_id", "")
        title_key   = p["title"].lower()[:60]

        if arxiv_id and arxiv_id in seen_ids:
            continue
        if title_key in seen_titles:
            continue

        if arxiv_id:
            seen_ids.add(arxiv_id)
        seen_titles.add(title_key)
        unique.append(p)

    return unique


def chunk_paper(paper: dict, chunk_size: int = 800, overlap: int = 100) -> list:
    """Chunk a paper's title + abstract into overlapping word windows."""
    full_text = f"Title: {paper['title']}\n\nAbstract: {paper['abstract']}"
    words     = full_text.split()
    chunks    = []
    start     = 0

    while start < len(words):
        end   = min(start + chunk_size, len(words))
        chunk = " ".join(words[start:end])
        chunks.append({
            "chunk_id":   f"{paper['id']}_chunk_{len(chunks)}",
            "paper_id":   paper["id"],
            "source":     paper["source"],
            "arxiv_id":   paper.get("arxiv_id", ""),
            "title":      paper["title"],
            "authors":    ", ".join(paper.get("authors", [])[:3]),
            "published":  paper.get("published", ""),
            "url":        paper.get("url", ""),
            "pdf_url":    paper.get("pdf_url", ""),
            "categories": ", ".join(paper.get("categories", [])),
            "text":       chunk,
        })
        if end == len(words):
            break
        start += chunk_size - overlap

    return chunks


def build_vectorstore(chunks: list, cfg: dict):
    """Embed chunks and store in ChromaDB."""
    store_path  = cfg["embeddings"]["vector_store_path"]
    collection  = cfg["embeddings"]["collection_name"]
    model_name  = cfg["embeddings"]["model"]

    Path(store_path).mkdir(parents=True, exist_ok=True)

    logger.info(f"Loading embedding model: {model_name}")
    model = SentenceTransformer(model_name)

    texts      = [c["text"] for c in chunks]
    batch_size = 64
    embeddings = []
    for i in range(0, len(texts), batch_size):
        batch = texts[i:i+batch_size]
        embs  = model.encode(batch, show_progress_bar=False)
        embeddings.extend(embs.tolist())
        if i % 200 == 0:
            logger.info(f"  Embedded {i}/{len(texts)}")

    client = chromadb.PersistentClient(
        path=store_path,
        settings=Settings(anonymized_telemetry=False)
    )
    try:
        client.delete_collection(collection)
        logger.info(f"Deleted existing collection: {collection}")
    except Exception:
        pass

    col = client.create_collection(
        name=collection,
        metadata={"hnsw:space": "cosine"}
    )

    for i in range(0, len(chunks), batch_size):
        batch_chunks = chunks[i:i+batch_size]
        batch_embs   = embeddings[i:i+batch_size]
        col.add(
            ids        = [c["chunk_id"] for c in batch_chunks],
            embeddings = batch_embs,
            documents  = [c["text"] for c in batch_chunks],
            metadatas  = [{
                "title":     c["title"],
                "authors":   c["authors"],
                "published": c["published"],
                "source":    c["source"],
                "arxiv_id":  c["arxiv_id"],
                "url":       c["url"],
                "pdf_url":   c["pdf_url"],
            } for c in batch_chunks]
        )

    logger.success(f"Vector store built: {col.count()} chunks from {len(set(c['paper_id'] for c in chunks))} papers")
    return col


def run_ingestion(config_path="configs/config.yaml", max_per_query=30):
    cfg = load_config(config_path)

    all_papers = []

    # ── arXiv ──────────────────────────────────────────────────────────
    logger.info(f"Fetching from arXiv ({len(ARXIV_QUERIES)} queries × {max_per_query} papers)")
    for query in ARXIV_QUERIES:
        papers = fetch_arxiv(query, max_results=max_per_query)
        all_papers.extend(papers)
        logger.info(f"  arXiv '{query[:40]}': {len(papers)} papers")
        time.sleep(3)  # respect arXiv rate limit

    # ── Semantic Scholar ───────────────────────────────────────────────
    logger.info(f"Fetching from Semantic Scholar ({len(SEMANTIC_SCHOLAR_QUERIES)} queries)")
    for query in SEMANTIC_SCHOLAR_QUERIES:
        papers = fetch_semantic_scholar(query, max_results=20)
        all_papers.extend(papers)
        logger.info(f"  S2 '{query[:40]}': {len(papers)} papers")
        time.sleep(2)  # be polite

    # ── Deduplicate ────────────────────────────────────────────────────
    all_papers = deduplicate(all_papers)
    logger.info(f"Unique papers after deduplication: {len(all_papers)}")

    # ── Save raw papers ────────────────────────────────────────────────
    raw_path = Path("knowledge_base/papers.json")
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    with open(raw_path, "w") as f:
        json.dump({"fetched_at": datetime.now().isoformat(),
                   "total": len(all_papers), "papers": all_papers}, f, indent=2)

    # ── Chunk ──────────────────────────────────────────────────────────
    all_chunks = []
    for paper in all_papers:
        all_chunks.extend(chunk_paper(paper,
            chunk_size=cfg["retrieval"].get("chunk_size", 800),
            overlap=100))
    logger.info(f"Total chunks: {len(all_chunks)}")

    # ── Embed + Store ──────────────────────────────────────────────────
    build_vectorstore(all_chunks, cfg)

    logger.success(f"Ingestion complete: {len(all_papers)} papers → {len(all_chunks)} chunks")
    return all_papers, all_chunks


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--max",    type=int, default=30, help="Max papers per arXiv query")
    parser.add_argument("--config", default="configs/config.yaml")
    args = parser.parse_args()
    run_ingestion(args.config, args.max)