"""Repair a work in the Kantor RAG index using clean OCR text.

Usage: replace_work(title, pages) where pages = {page_no: clean_text}.
- Removes ALL existing chunks of that work whose page range is inside the
  OCR'd page set; re-chunks the clean text page-aware (~800 chars);
  embeds with nomic (NO prefix — matches how the index was built);
  rebuilds index.faiss + index_data.pkl + index_summary.json.
"""
import pickle, json, re, faiss
import numpy as np
from sentence_transformers import SentenceTransformer

DB = "database"
CHUNK_SIZE = 800

_model = None
def model():
    global _model
    if _model is None:
        _model = SentenceTransformer("nomic-ai/nomic-embed-text-v1.5", trust_remote_code=True)
    return _model


def clean_ocr(text):
    """Cleanup of Unlimited-OCR output: layout markers, html tables, images."""
    # blank-page hallucination
    if "contains no text" in text or "Ground Truth" in text:
        return ""
    text = re.sub(r"<\|det\|>\w+\s*\[[\d,\s]*\]?<\|/det\|>", " ", text)  # det markers
    text = re.sub(r"<\|[^>]{0,40}?\|>", " ", text)         # any other special tokens
    text = re.sub(r"!\[.*?\]\(.*?\)", "", text)            # images
    text = re.sub(r"</(td|th)>\s*<(td|th)>", " | ", text)  # table cells -> pipes
    text = re.sub(r"</tr>\s*<tr>", "\n", text)
    text = re.sub(r"<[^>]{1,30}>", " ", text)              # remaining html tags
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def chunk_pages(pages, chunk_size=CHUNK_SIZE):
    """pages: dict {page_no: text}. Returns list of (text, start_page, end_page).
    Concatenates pages in order and cuts ~chunk_size chars on word boundaries,
    tracking which pages each chunk covers (mimics original page-aware chunking)."""
    # build char -> page map
    parts, page_of_char = [], []
    for p in sorted(pages):
        t = clean_ocr(pages[p])
        if not t:
            continue
        parts.append(t)
        page_of_char.extend([p] * (len(t) + 1))  # +1 for joining newline
    full = "\n".join(parts)
    page_of_char = page_of_char[:len(full)]
    chunks, pos = [], 0
    while pos < len(full):
        end = min(pos + chunk_size, len(full))
        if end < len(full):
            sp = full.rfind(" ", pos + int(chunk_size * 0.6), end)
            nl = full.rfind("\n", pos + int(chunk_size * 0.6), end)
            cut = max(sp, nl)
            if cut > pos:
                end = cut
        text = full[pos:end].strip()
        if len(text) >= 40:
            chunks.append((text, page_of_char[pos], page_of_char[min(end, len(full)-1)]))
        pos = end + 1
    return chunks


def replace_work(title, pages, db=DB):
    with open(f"{db}/index_data.pkl", "rb") as f:
        data = pickle.load(f)
    texts, metas = data["texts"], data["metadatas"]
    index = faiss.read_index(f"{db}/index.faiss")
    assert index.ntotal == len(texts)

    page_set = set(pages)
    keep, remove_meta = [], None
    for i, m in enumerate(metas):
        if m.get("title") == title:
            s, e = m.get("start_page") or 0, m.get("end_page") or m.get("start_page") or 0
            if set(range(s, e + 1)) & page_set:
                remove_meta = dict(m)
                continue
        keep.append(i)
    removed = len(texts) - len(keep)
    if removed == 0 or remove_meta is None:
        raise SystemExit(f"No chunks matched title={title!r} pages={sorted(page_set)}")

    new_chunks = chunk_pages(pages)
    new_texts = [c[0] for c in new_chunks]
    new_metas = []
    for text, sp, ep in new_chunks:
        m = {k: v for k, v in remove_meta.items() if k not in ("start_page", "end_page")}
        m["start_page"], m["end_page"] = sp, ep
        new_metas.append(m)

    # embeddings: keep old vectors, embed new texts (no prefix, matches index)
    old_vecs = index.reconstruct_n(0, index.ntotal)
    kept_vecs = old_vecs[keep]
    new_vecs = model().encode(new_texts, normalize_embeddings=True,
                              batch_size=16, show_progress_bar=False).astype("float32")
    all_vecs = np.vstack([kept_vecs, new_vecs])

    out_texts = [texts[i] for i in keep] + new_texts
    out_metas = [metas[i] for i in keep] + new_metas

    new_index = faiss.IndexFlatIP(all_vecs.shape[1])
    new_index.add(all_vecs)
    faiss.write_index(new_index, f"{db}/index.faiss")
    with open(f"{db}/index_data.pkl", "wb") as f:
        pickle.dump({"texts": out_texts, "metadatas": out_metas}, f)
    try:
        summ = json.load(open(f"{db}/index_summary.json"))
        summ["total_chunks"] = len(out_texts)
        json.dump(summ, open(f"{db}/index_summary.json", "w"), indent=2)
    except Exception as e:
        print("summary update skipped:", e)
    print(f"OK: removed {removed} old chunks, added {len(new_texts)} clean chunks "
          f"(index: {index.ntotal} -> {new_index.ntotal})")


if __name__ == "__main__":
    import sys, pathlib
    title = "Interbehavioral psychology and scientific analysis of data and operations"
    pages = {}
    for f in pathlib.Path("ocr_out").glob("ibp_1956_p*.md"):
        n = int(re.search(r"p(\d+)\.md", f.name).group(1))
        pages[n] = f.read_text()
    replace_work(title, pages)
