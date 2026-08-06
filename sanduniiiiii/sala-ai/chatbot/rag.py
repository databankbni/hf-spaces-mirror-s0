"""
Sala AI - RAG Layer
ChromaDB vector store for sala.lk products (and optional PDF ingestion)
"""

import os
import re
import logging
from datetime import datetime, timezone
from typing import Optional

from langchain_chroma import Chroma
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.documents import Document

from data_sources.woocommerce import fetch_all_products, products_to_documents

log = logging.getLogger("SalaAI")

VECTOR_DB_PATH = "./chroma_db/products"
WIKI_DB_PATH = "./chroma_db/wiki"

TESSERACT_CMD = os.getenv("TESSERACT_CMD")

BROAD_QUERY_PARAMS = {"k": 12, "fetch_k": 35, "lambda_mult": 0.5}
SPECIFIC_QUERY_PARAMS = {"k": 6, "fetch_k": 20, "lambda_mult": 0.5}
BROAD_QUERY_MAX_WORDS = 6

CATEGORY_FILTER_MAX_K = 40

EMBEDDING_MODEL_NAME = "paraphrase-multilingual-MiniLM-L12-v2"

_embeddings: Optional[HuggingFaceEmbeddings] = None
_product_store: Optional[Chroma] = None

_wiki_store: Optional[Chroma] = None
_wiki_retriever = None

_known_categories: set[str] = set()


def get_embeddings() -> HuggingFaceEmbeddings:
    global _embeddings
    if _embeddings is None:
        _embeddings = HuggingFaceEmbeddings(model_name=EMBEDDING_MODEL_NAME)
    return _embeddings


def restore_wiki_db_from_backup():
    """
    Pulls the wiki vector DB (./chroma_db/wiki) down from a private Hugging
    Face Dataset repo used as persistent backup storage, before
    load_wiki_db() runs. This host's local disk does NOT survive a code
    redeploy, so without this, any wiki entries (including announcements)
    added via the admin dashboard would be lost every time the app is
    redeployed.

    Configure via two environment variables / Space secrets:
      - WIKI_BACKUP_REPO_ID: e.g. "sanduniiiiii/sala-ai-wiki-backup"
      - HF_TOKEN: a Hugging Face access token with WRITE access to that repo
        (needed here for restore, and later for backup_wiki_db_to_hub())

    If either is missing, or no backup exists yet (e.g. very first deploy),
    this is a safe no-op - the app just starts with whatever's on local
    disk (possibly empty), same as before this was implemented.
    """
    repo_id = os.environ.get("WIKI_BACKUP_REPO_ID")
    hf_token = os.environ.get("HF_TOKEN")

    if not repo_id or not hf_token:
        log.warning(
            "WIKI_BACKUP_REPO_ID / HF_TOKEN not configured - skipping wiki "
            "DB restore. Wiki entries added via the dashboard will NOT "
            "survive a redeploy until these secrets are set."
        )
        return None

    try:
        from huggingface_hub import snapshot_download
        import shutil

        cache_path = snapshot_download(
            repo_id=repo_id,
            repo_type="dataset",
            token=hf_token,
        )
        # snapshot_download() returns a read-only HF cache directory - copy
        # its contents into our actual WIKI_DB_PATH so Chroma can open
        # (and later write to) it normally.
        if os.path.exists(WIKI_DB_PATH):
            shutil.rmtree(WIKI_DB_PATH)
        shutil.copytree(cache_path, WIKI_DB_PATH)
        log.info(f"Wiki DB restored from backup repo '{repo_id}'")
        return WIKI_DB_PATH
    except Exception as e:
        # Most common case: the backup repo doesn't exist yet (first time
        # this is configured, before any backup has been pushed). That's
        # expected and fine - just start empty and let the first
        # backup_wiki_db_to_hub() call create it.
        log.warning(f"Wiki DB restore skipped (no backup yet, or restore failed): {e}")
        return None


def backup_wiki_db_to_hub():
    """
    Pushes the current wiki vector DB (./chroma_db/wiki) up to the private
    HF Dataset repo configured via WIKI_BACKUP_REPO_ID / HF_TOKEN, so it
    survives the next redeploy. Called automatically after every wiki write
    (add_wiki_text, add_wiki_pdf, delete_wiki_document below).
    Safe no-op if the backup repo isn't configured - errors are logged but
    never raised, so a backup failure never breaks the actual save/delete
    the admin just performed.
    """
    repo_id = os.environ.get("WIKI_BACKUP_REPO_ID")
    hf_token = os.environ.get("HF_TOKEN")

    if not repo_id or not hf_token:
        return  # not configured - already warned about this at startup

    try:
        from huggingface_hub import HfApi
        api = HfApi(token=hf_token)
        api.create_repo(repo_id=repo_id, repo_type="dataset", private=True, exist_ok=True)
        api.upload_folder(
            repo_id=repo_id,
            repo_type="dataset",
            folder_path=WIKI_DB_PATH,
            path_in_repo=".",
            commit_message="Auto-backup wiki DB",
        )
        log.info(f"Wiki DB backed up to '{repo_id}'")
    except Exception as e:
        log.error(f"Wiki DB backup failed (local save still succeeded): {e}")


def _rebuild_known_categories():
    """Pull every distinct category string out of the current product DB."""
    global _known_categories
    _known_categories = set()
    if _product_store is None:
        return
    try:
        results = _product_store.get(include=["metadatas"])
        for meta in results.get("metadatas", []):
            cat_field = meta.get("category", "")
            for part in cat_field.split(","):
                part = part.strip()
                if part:
                    _known_categories.add(part)
        log.info(f"Known categories loaded: {sorted(_known_categories)}")
    except Exception as e:
        log.error(f"Failed to build category list: {e}")


def load_product_db():
    """Load existing product vector DB, or build fresh from WooCommerce if missing."""
    global _product_store
    embeddings = get_embeddings()

    if os.path.exists(VECTOR_DB_PATH):
        log.info("Loading existing product vector DB...")
        _product_store = Chroma(
            persist_directory=VECTOR_DB_PATH,
            embedding_function=embeddings,
        )
    else:
        log.info("No existing DB found - fetching fresh from WooCommerce...")
        _product_store = refresh_product_db()
        _rebuild_known_categories()
        return

    count = _product_store._collection.count()
    log.info(f"Product DB loaded: {count} products")
    _rebuild_known_categories()


def refresh_product_db():
    """Fetch fresh products from WooCommerce and rebuild the vector DB."""
    global _product_store
    embeddings = get_embeddings()

    products = fetch_all_products()
    if not products:
        log.warning("No products fetched - staying in general mode")
        return None

    docs = products_to_documents(products)

    import shutil
    if os.path.exists(VECTOR_DB_PATH):
        shutil.rmtree(VECTOR_DB_PATH)
        log.info("Old product DB cleared")

    _product_store = Chroma.from_documents(
        docs,
        embeddings,
        persist_directory=VECTOR_DB_PATH,
    )
    log.info(f"Product DB refreshed: {len(docs)} products indexed")
    _rebuild_known_categories()
    return _product_store


def backfill_category_metadata() -> dict:
    """
    ONE-TIME FIX: The product DB was originally indexed before category
    metadata was added to products_to_documents(). Rather than waiting on
    the WooCommerce connection (currently blocked by a hosting-side firewall
    issue returning 403 on every request), this extracts the category
    directly from each document's already-embedded "Category: ..." text line
    and backfills it into that document's metadata in-place.
    This needs NO WooCommerce API call - it works entirely off data already
    sitting in the vector DB from the last successful index. Once the
    WooCommerce/firewall issue is resolved, a normal refresh_product_db()
    call will re-index everything properly and this backfill becomes
    unnecessary (but is harmless to leave in place / re-run).
    """
    global _product_store
    if _product_store is None:
        return {"status": "failed", "message": "Product DB not loaded"}

    try:
        results = _product_store.get(include=["documents", "metadatas"])
        ids = results["ids"]
        docs = results["documents"]
        metadatas = results["metadatas"]

        updated_count = 0
        new_metadatas = []
        for doc_text, meta in zip(docs, metadatas):
            match = re.search(r"Category:\s*(.+)", doc_text)
            new_meta = dict(meta)  # copy, don't mutate the original in place
            if match:
                category_str = match.group(1).strip().lower()
                if new_meta.get("category") != category_str:
                    new_meta["category"] = category_str
                    updated_count += 1
            new_metadatas.append(new_meta)

        if ids:
            _product_store._collection.update(ids=ids, metadatas=new_metadatas)

        _rebuild_known_categories()
        log.info(f"Category backfill complete: {updated_count}/{len(ids)} products updated")
        return {"status": "success", "updated": updated_count, "total": len(ids)}
    except Exception as e:
        log.error(f"Category backfill error: {e}")
        return {"status": "failed", "message": str(e)}


def _pick_search_params(user_query: str) -> dict:
    word_count = len(user_query.split())
    has_digit = any(ch.isdigit() for ch in user_query)

    if has_digit or word_count > BROAD_QUERY_MAX_WORDS:
        return SPECIFIC_QUERY_PARAMS
    return BROAD_QUERY_PARAMS


def _match_known_category(user_query: str) -> Optional[str]:
    """
    Check if the user's query matches (or contains) a known product category
    exactly, e.g. "ups", "online ups", "wi-fi extender". Returns the matched
    category string (lowercase, as stored in metadata) or None.
    Longest match wins, so "online ups" matches before the generic "ups".
    """
    query_lower = user_query.lower().strip()
    matches = [cat for cat in _known_categories if cat in query_lower or query_lower in cat]
    if not matches:
        return None
    return max(matches, key=len)


def get_product_context(user_query: str) -> Optional[str]:
    """Retrieve relevant product context for a user query."""
    if not _product_store:
        return None
    try:
        matched_category = _match_known_category(user_query)
        if matched_category:
            all_results = _product_store.get(include=["documents", "metadatas"])
            docs_text = []
            seen = set()
            for doc_text, meta in zip(all_results["documents"], all_results["metadatas"]):
                cat_field = meta.get("category", "")
                if matched_category in cat_field:
                    key = meta.get("id") or meta.get("name")
                    if key not in seen:
                        seen.add(key)
                        docs_text.append(doc_text)
            if docs_text:
                docs_text = docs_text[:CATEGORY_FILTER_MAX_K]
                log.info(f"Category filter matched '{matched_category}': {len(docs_text)} products")
                return "\n\n---\n\n".join(docs_text)

        params = _pick_search_params(user_query)
        docs = _product_store.max_marginal_relevance_search(
            user_query,
            k=params["k"],
            fetch_k=params["fetch_k"],
            lambda_mult=params["lambda_mult"],
        )
        if docs:
            seen = set()
            unique_docs = []
            for d in docs:
                key = d.metadata.get("id") or d.metadata.get("name") or d.page_content
                if key not in seen:
                    seen.add(key)
                    unique_docs.append(d)
            return "\n\n---\n\n".join(d.page_content for d in unique_docs)
    except Exception as e:
        log.error(f"Product retrieval error: {e}")
    return None


def ingest_pdf(pdf_path: str, chunk_size: int = 700, chunk_overlap: int = 150):
    """Optional: ingest a PDF (e.g. product manual) into a separate retriever."""
    if not os.path.exists(pdf_path):
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    loader = PyPDFLoader(pdf_path)
    documents = loader.load()
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size, chunk_overlap=chunk_overlap
    )
    chunks = splitter.split_documents(documents)

    embeddings = get_embeddings()
    pdf_store = Chroma.from_documents(chunks, embeddings)
    pdf_retriever = pdf_store.as_retriever(search_kwargs={"k": 5})

    log.info(f"PDF ingested: {len(chunks)} chunks from {os.path.basename(pdf_path)}")
    return pdf_retriever, len(chunks)


def load_wiki_db():
    """Load existing wiki vector DB if present. Call this once at app startup."""
    global _wiki_store, _wiki_retriever
    embeddings = get_embeddings()

    if os.path.exists(WIKI_DB_PATH):
        _wiki_store = Chroma(
            persist_directory=WIKI_DB_PATH,
            embedding_function=embeddings,
        )
        _wiki_retriever = _wiki_store.as_retriever(
            search_kwargs={"k": 5},
            search_type="similarity",
        )
        count = _wiki_store._collection.count()
        log.info(f"Wiki DB loaded: {count} entries")
    else:
        log.info("No wiki DB found yet - will be created on first upload")


def add_wiki_text(
    title: str,
    content: str,
    chunk_size: int = 700,
    chunk_overlap: int = 150,
    is_announcement: bool = False,
) -> int:
    """
    Add a wiki/FAQ text entry into the wiki vector DB. Returns total chunk count.
    When is_announcement=True, every chunk of this entry is tagged so it can
    be surfaced proactively to users the moment they open the chat widget
    (see get_active_announcement() below), instead of only being retrieved
    when a matching question is asked.
    """
    global _wiki_store, _wiki_retriever
    embeddings = get_embeddings()

    created_at = datetime.now(timezone.utc).isoformat()

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size, chunk_overlap=chunk_overlap
    )
    docs = splitter.create_documents(
        [content],
        metadatas=[
            {
                "title": title,
                "is_announcement": is_announcement,
                "created_at": created_at,
            }
        ],
    )
    # give each chunk of this entry an explicit order index, so an
    # announcement's chunks can be reassembled in the right order later
    for i, d in enumerate(docs):
        d.metadata["chunk_index"] = i

    if _wiki_store is None:
        _wiki_store = Chroma.from_documents(
            docs, embeddings, persist_directory=WIKI_DB_PATH
        )
    else:
        _wiki_store.add_documents(docs)

    _wiki_retriever = _wiki_store.as_retriever(
        search_kwargs={"k": 5}, search_type="similarity"
    )
    count = _wiki_store._collection.count()
    log.info(f"Wiki entry '{title}' added (announcement={is_announcement}). Total chunks: {count}")
    backup_wiki_db_to_hub()
    return count


def get_active_announcement() -> Optional[dict]:
    """
    Returns the most recently uploaded wiki entry marked is_announcement=True,
    reassembled into a single block of text - or None if there are no
    announcements in the wiki DB (or the DB isn't loaded yet).
    Used by GET /chat/announcement (chatbot/routes.py) so the widget can show
    it as an automatic message right after the greeting, without the user
    having to ask anything.
    """
    if _wiki_store is None:
        return None
    try:
        results = _wiki_store.get(
            where={"is_announcement": True}, include=["documents", "metadatas"]
        )
        metadatas = results.get("metadatas", [])
        documents = results.get("documents", [])
        if not metadatas:
            return None

        # find the title with the newest created_at timestamp
        latest_title = None
        latest_ts = None
        for meta in metadatas:
            ts = meta.get("created_at", "")
            if latest_ts is None or ts > latest_ts:
                latest_ts = ts
                latest_title = meta.get("title")

        # gather every chunk belonging to that title, in the original order
        chunks = [
            (meta.get("chunk_index", 0), doc)
            for doc, meta in zip(documents, metadatas)
            if meta.get("title") == latest_title
        ]
        chunks.sort(key=lambda pair: pair[0])
        full_content = " ".join(doc for _, doc in chunks).strip()

        if not full_content:
            return None

        return {"title": latest_title, "content": full_content, "created_at": latest_ts}
    except Exception as e:
        log.error(f"Active announcement retrieval error: {e}")
        return None


def _extract_pdf_text_with_ocr(pdf_path: str) -> list[Document]:
    """
    Fallback text extraction for scanned/photo PDFs using OCR.
    Converts each page to an image, then runs Tesseract on it.
    """
    import pytesseract
    from pdf2image import convert_from_path

    if TESSERACT_CMD:
        pytesseract.pytesseract.tesseract_cmd = TESSERACT_CMD

    log.info(f"Falling back to OCR for {os.path.basename(pdf_path)}...")
    pages = convert_from_path(pdf_path, dpi=300)

    documents = []
    for i, page_image in enumerate(pages):
        text = pytesseract.image_to_string(page_image, lang="sin+eng")
        if text.strip():
            documents.append(
                Document(page_content=text, metadata={"page": i + 1})
            )
    log.info(f"OCR extracted text from {len(documents)}/{len(pages)} pages")
    return documents


def add_wiki_pdf(pdf_path: str, chunk_size: int = 700, chunk_overlap: int = 150, display_name: str | None = None) -> int:
    """
    Ingest a PDF (manual, FAQ doc, scanned photo, etc.) into the wiki vector DB.
    """
    global _wiki_store, _wiki_retriever
    if not os.path.exists(pdf_path):
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    loader = PyPDFLoader(pdf_path)
    documents = loader.load()

    total_text = "".join(d.page_content.strip() for d in documents)
    if not total_text:
        documents = _extract_pdf_text_with_ocr(pdf_path)

    if not documents:
        raise ValueError(
            "No text could be extracted from this PDF, even with OCR. "
            "The image quality may be too low."
        )

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size, chunk_overlap=chunk_overlap
    )
    chunks = splitter.split_documents(documents)

    title = display_name or os.path.basename(pdf_path)
    for c in chunks:
        c.metadata["title"] = title

    embeddings = get_embeddings()
    if _wiki_store is None:
        _wiki_store = Chroma.from_documents(
            chunks, embeddings, persist_directory=WIKI_DB_PATH
        )
    else:
        _wiki_store.add_documents(chunks)

    _wiki_retriever = _wiki_store.as_retriever(
        search_kwargs={"k": 5}, search_type="similarity"
    )
    count = _wiki_store._collection.count()
    log.info(f"Wiki PDF '{title}' ingested: {len(chunks)} chunks. Total chunks: {count}")
    backup_wiki_db_to_hub()
    return count


def get_wiki_context(user_query: str) -> Optional[str]:
    """Retrieve relevant wiki context for a user query."""
    if not _wiki_retriever:
        return None
    try:
        docs = _wiki_retriever.invoke(user_query)
        if docs:
            return "\n\n---\n\n".join(d.page_content for d in docs)
    except Exception as e:
        log.error(f"Wiki retrieval error: {e}")
    return None


def list_wiki_documents() -> list[dict]:
    """
    Returns a summary of unique uploaded wiki documents (grouped by title),
    with their chunk counts and whether each is marked as an announcement.
    Used by the admin dashboard's file list.
    """
    if _wiki_store is None:
        return []
    try:
        results = _wiki_store.get(include=["metadatas"])
        titles = {}
        for meta in results.get("metadatas", []):
            title = meta.get("title", "Untitled")
            if title not in titles:
                titles[title] = {"chunks": 0, "is_announcement": False}
            titles[title]["chunks"] += 1
            if meta.get("is_announcement"):
                titles[title]["is_announcement"] = True
        return [
            {"title": t, "chunks": info["chunks"], "is_announcement": info["is_announcement"]}
            for t, info in sorted(titles.items())
        ]
    except Exception as e:
        log.error(f"Wiki list error: {e}")
        return []


def delete_wiki_document(title: str) -> int:
    """
    Deletes all chunks belonging to a specific uploaded document (by title).
    Returns the number of chunks deleted.
    """
    global _wiki_store
    if _wiki_store is None:
        return 0
    try:
        existing = _wiki_store.get(where={"title": title}, include=["metadatas"])
        ids_to_delete = existing.get("ids", [])
        if not ids_to_delete:
            return 0
        _wiki_store.delete(ids=ids_to_delete)
        log.info(f"Deleted wiki document '{title}': {len(ids_to_delete)} chunks removed")
        backup_wiki_db_to_hub()
        return len(ids_to_delete)
    except Exception as e:
        log.error(f"Wiki delete error: {e}")
        raise