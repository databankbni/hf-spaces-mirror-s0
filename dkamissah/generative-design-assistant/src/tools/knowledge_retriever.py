"""
Tool 2: Engineering Knowledge Retriever

Queries the ChromaDB knowledge base of engineering standards,
material specs, and design guidelines to inform design generation.
"""

import os
import re
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


class KnowledgeRetriever:
    def __init__(self, config_path="configs/config.yaml"):
        cfg        = load_config(config_path)
        store_path = cfg["embeddings"]["vector_store_path"]
        collection = cfg["embeddings"]["collection_name"]
        model_name = cfg["embeddings"]["model"]
        self.top_k = cfg["retrieval"]["top_k"]

        self.model = SentenceTransformer(model_name)
        client = chromadb.PersistentClient(
            path=store_path,
            settings=Settings(anonymized_telemetry=False)
        )
        self.collection = client.get_collection(collection)
        logger.info(f"KnowledgeRetriever ready — {self.collection.count()} documents")

    def retrieve(self, query: str, category: str = None) -> list:
        """Retrieve relevant engineering knowledge for a given query."""
        emb     = self.model.encode([query]).tolist()
        where   = {"category": category} if category else None
        results = self.collection.query(
            query_embeddings = emb,
            n_results        = self.top_k,
            include          = ["documents", "metadatas", "distances"],
            where            = where,
        )

        chunks = []
        for doc, meta, dist in zip(
            results["documents"][0],
            results["metadatas"][0],
            results["distances"][0]
        ):
            chunks.append({
                "title":    meta.get("title", ""),
                "authors":  meta.get("authors", ""),
                "published": meta.get("published", ""),
                "source":   meta.get("source", ""),
                "arxiv_id": meta.get("arxiv_id", ""),
                "url":      meta.get("url", ""),
                "text":     doc,
                "score":    round(1 - dist, 4),
                "meta":     meta,
            })
        return chunks

    def retrieve_for_requirements(self, requirements: dict) -> dict:
        """Retrieve knowledge across multiple relevant categories."""
        priority = requirements.get("priority", "performance")
        component = requirements.get("component_name", "")
        constraints = " ".join(requirements.get("constraints", []))

        queries = {
            "materials":      f"material selection {component} {priority} automotive",
            "design_methods": f"design optimisation {component} lightweight generative",
            "standards":      f"manufacturing tolerances standards {component} {constraints}",
            "sustainability":  f"sustainable design recyclability {component}",
        }

        knowledge = {}
        for category, query in queries.items():
            results = self.retrieve(query, category=category if category != "all" else None)
            if results:
                knowledge[category] = results[0]  # top result per category

        logger.info(f"Retrieved knowledge across {len(knowledge)} categories")
        return knowledge

    def format_context(self, knowledge: dict) -> str:
        parts = []
        for category, doc in knowledge.items():
            meta = doc.get("meta", {})
            source = meta.get("url", "") or meta.get("pdf_url", "")
            parts.append(
                f"[{doc['title']}] ({meta.get('published', '')})"
                f"\nSource: {source}"
                f"\n{doc['text'][:400]}..."
            )
        return "\n\n---\n\n".join(parts)
