import os
import json
import hashlib
from pathlib import Path
from typing import Dict, List

from dotenv import load_dotenv
from langchain_openai import OpenAIEmbeddings
from langchain_community.vectorstores import Chroma
from langchain_text_splitters import (
    MarkdownHeaderTextSplitter,
    RecursiveCharacterTextSplitter,
)
from langchain_core.documents import Document

# Load environment variables from .env file if it exists
load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DB_DIR = BASE_DIR / "db"
STATE_FILE = DB_DIR / "ingestion_state.json"

# Folders to parse for the Vector DB
INGEST_DIRS = ["github", "raw", "linkedin", "static"]


def get_file_hash(filepath: Path) -> str:
    with open(filepath, "r", encoding="utf-8") as f:
        return hashlib.md5(f.read().encode("utf-8")).hexdigest()


def load_state() -> Dict[str, Dict]:
    """
    Returns state in this normalized format:
    {
        "data/static/public_profile.md": {
            "hash": "...",
            "chunk_ids": ["static_N/A_public_profile_chunk_0", ...]
        }
    }

    Supports old state format too:
    {
        "data/static/public_profile.md": "old_md5_hash"
    }
    """
    if not STATE_FILE.exists():
        return {}

    with open(STATE_FILE, "r", encoding="utf-8") as f:
        raw_state = json.load(f)

    if isinstance(raw_state, dict) and "files" in raw_state and isinstance(raw_state["files"], dict):
        normalized = {}
        for rel_path, entry in raw_state["files"].items():
            if isinstance(entry, dict):
                normalized[rel_path] = {
                    "hash": entry.get("hash", ""),
                    "chunk_ids": entry.get("chunk_ids", []),
                }
        return normalized

    normalized = {}
    if isinstance(raw_state, dict):
        for rel_path, value in raw_state.items():
            if isinstance(value, str):
                normalized[rel_path] = {
                    "hash": value,
                    "chunk_ids": [],
                }
            elif isinstance(value, dict):
                normalized[rel_path] = {
                    "hash": value.get("hash", ""),
                    "chunk_ids": value.get("chunk_ids", []),
                }
    return normalized


def save_state(state: Dict[str, Dict]) -> None:
    os.makedirs(DB_DIR, exist_ok=True)
    payload = {
        "version": 2,
        "files": state,
    }
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=4)


def process_markdown_file(filepath: Path, base_folder: str, rel_path: str) -> List[Document]:
    with open(filepath, "r", encoding="utf-8") as f:
        text = f.read()

    headers_to_split_on = [
        ("#", "Header 1"),
        ("##", "Header 2"),
        ("###", "Header 3"),
    ]
    markdown_splitter = MarkdownHeaderTextSplitter(headers_to_split_on=headers_to_split_on)
    md_header_splits = markdown_splitter.split_text(text)

    text_splitter = RecursiveCharacterTextSplitter(chunk_size=1200, chunk_overlap=150)
    splits = text_splitter.split_documents(md_header_splits)

    safe_name = filepath.stem.replace(" ", "_").replace(".", "_")

    project_name = "N/A"
    parts = list(filepath.relative_to(DATA_DIR).parts)
    if "github" in parts and len(parts) > 1:
        project_name = parts[1]

    for i, split in enumerate(splits):
        split.metadata["source"] = rel_path
        split.metadata["folder"] = base_folder
        split.metadata["project"] = project_name
        split.metadata["chunk_id"] = f"{base_folder}_{project_name}_{safe_name}_chunk_{i}"

    return splits


def process_json_file(filepath: Path, base_folder: str, rel_path: str) -> List[Document]:
    with open(filepath, "r", encoding="utf-8") as f:
        try:
            data = json.load(f)
        except Exception:
            data = None

    if filepath.name == "unknown_questions.json" and isinstance(data, list):
        docs = []
        for i, item in enumerate(data):
            if isinstance(item, dict) and "question" in item and "answer" in item:
                q = item.get("question", "").strip()
                a = item.get("answer", "").strip()
                content = f"### Verified Question & Answer\n**Question:** {q}\n**Answer:** {a}"
                docs.append(
                    Document(
                        page_content=content,
                        metadata={
                            "source": rel_path,
                            "folder": base_folder,
                            "project": "unknown_questions",
                            "chunk_id": f"unknown_q_{i}",
                        },
                    )
                )
        if docs:
            return docs

    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    project_name = "N/A"
    parts = list(filepath.relative_to(DATA_DIR).parts)
    if "github" in parts and len(parts) > 1:
        project_name = parts[1]

    safe_name = filepath.stem.replace(" ", "_").replace(".", "_")
    chunk_id = f"{base_folder}_{project_name}_{safe_name}_chunk_0"

    doc = Document(
        page_content=content,
        metadata={
            "source": rel_path,
            "folder": base_folder,
            "project": project_name,
            "chunk_id": chunk_id,
        },
    )
    return [doc]


def process_file(filepath: Path, base_folder: str, rel_path: str) -> List[Document]:
    if filepath.suffix == ".md":
        return process_markdown_file(filepath, base_folder, rel_path)
    if filepath.suffix == ".json":
        return process_json_file(filepath, base_folder, rel_path)
    return []


def main():
    if not os.getenv("OPENAI_API_KEY"):
        print("\n[ERROR] OPENAI_API_KEY not found in the environment.")
        print("Please set it or create a .env file containing OPENAI_API_KEY=your_key_here")
        return

    print("Initializing ChromaDB and OpenAI Embeddings...")
    embeddings = OpenAIEmbeddings(model="text-embedding-3-small")

    vectorstore = Chroma(
        collection_name="aruncore_knowledge",
        embedding_function=embeddings,
        persist_directory=str(DB_DIR),
    )

    previous_state = load_state()
    new_state: Dict[str, Dict] = {}

    docs_to_upsert: List[Document] = []
    ids_to_upsert: List[str] = []
    stale_ids_to_delete = set()
    current_rel_paths = set()

    folders_to_scan = [folder for folder in INGEST_DIRS if (DATA_DIR / folder).is_dir()]

    for folder in folders_to_scan:
        target_dir = DATA_DIR / folder

        for ext in ["*.md", "*.json"]:
            for filepath in target_dir.rglob(ext):
                if "test_set" in filepath.parts:
                    continue

                rel_path = filepath.relative_to(BASE_DIR).as_posix()
                current_rel_paths.add(rel_path)

                file_hash = get_file_hash(filepath)
                previous_entry = previous_state.get(rel_path, {})
                previous_hash = previous_entry.get("hash")
                previous_chunk_ids = previous_entry.get("chunk_ids", [])

                is_unchanged = (
                    previous_hash == file_hash
                    and isinstance(previous_chunk_ids, list)
                    and len(previous_chunk_ids) > 0
                )

                if is_unchanged:
                    new_state[rel_path] = {
                        "hash": previous_hash,
                        "chunk_ids": previous_chunk_ids,
                    }
                    continue

                print(f"File changed/new -> Processing: {rel_path}")

                splits = process_file(filepath, folder, rel_path)
                new_chunk_ids = [doc.metadata["chunk_id"] for doc in splits]

                docs_to_upsert.extend(splits)
                ids_to_upsert.extend(new_chunk_ids)

                old_ids_set = set(previous_chunk_ids)
                new_ids_set = set(new_chunk_ids)

                stale_ids_to_delete.update(old_ids_set - new_ids_set)

                new_state[rel_path] = {
                    "hash": file_hash,
                    "chunk_ids": new_chunk_ids,
                }

    deleted_files = set(previous_state.keys()) - current_rel_paths
    for rel_path in deleted_files:
        old_chunk_ids = previous_state.get(rel_path, {}).get("chunk_ids", [])
        if old_chunk_ids:
            print(f"File deleted -> Removing old chunks: {rel_path}")
            stale_ids_to_delete.update(old_chunk_ids)

    if docs_to_upsert:
        print(f"\nUpserting {len(docs_to_upsert)} new/modified chunks into Vector DB...")
        vectorstore.add_documents(documents=docs_to_upsert, ids=ids_to_upsert)
        print("Upsert complete.")
    else:
        print("\nNo new or modified files to upsert.")

    if stale_ids_to_delete:
        stale_ids_list = sorted(stale_ids_to_delete)
        print(f"Deleting {len(stale_ids_list)} stale chunks from Vector DB...")
        vectorstore.delete(ids=stale_ids_list)
        print("Stale chunk cleanup complete.")
    else:
        print("No stale chunks to delete.")

    save_state(new_state)
    print("Ingestion sequence complete.")


if __name__ == "__main__":
    main()
