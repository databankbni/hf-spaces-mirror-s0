import os
import re
import pickle
from docx import Document
from sentence_transformers import SentenceTransformer
import faiss
import numpy as np

DOCUMENT_FOLDER = "nba/documents"
VECTOR_FOLDER = "nba/vector_store"

# Lazy-loaded: importing this module must NOT trigger a model download/load.
# The model is only loaded the first time it's actually needed (e.g. when a
# document is uploaded or the index is rebuilt), not at server import/startup.
_model = None


def _get_model():
    global _model
    if _model is None:
        print("Loading NBA embedding model (lazy)...")
        _model = SentenceTransformer("all-MiniLM-L6-v2")
    return _model


def read_docx(file_path):
    doc = Document(file_path)
    text = []
    for para in doc.paragraphs:
        if para.text.strip():
            text.append(para.text.strip())
    return "\n".join(text)


def extract_major_issue(text, filename):
    lines = [line.strip() for line in text.split("\n") if line.strip()]
    if lines:
        match = re.search(r"Major\s+Issue\s*:\s*(.*)", lines[0], re.IGNORECASE)
        if match:
            return match.group(1).strip()
    name = filename.replace(".docx", "")
    name = re.sub(r"Major\s*Issue[_ ]*", "", name, flags=re.IGNORECASE)
    name = name.replace("_", " ").strip()
    return name


def split_subissues(text, major_issue):
    text = re.sub(r"Major\s+Issue\s*:\s*.*?\n", "", text, count=1, flags=re.IGNORECASE)
    parts = re.split(r"\n(?=\d+\.?\s+)", text)
    chunks = []
    for part in parts:
        part = part.strip()
        if not part:
            continue
        first_line = part.split("\n")[0]
        complaint = re.sub(r"^\d+\.?\s*", "", first_line)
        complaint = re.sub(r"\s+", " ", complaint).strip()
        final_chunk = f"""Major Issue: {major_issue}

Sub Issue: {complaint}

{part}
"""
        chunks.append({
            "text": final_chunk,
            "major_issue": major_issue,
            "sub_issue": complaint,
        })
    return chunks


def load_existing_index():
    index_path = os.path.join(VECTOR_FOLDER, "nba_index.faiss")
    metadata_path = os.path.join(VECTOR_FOLDER, "metadata.pkl")
    embeddings_path = os.path.join(VECTOR_FOLDER, "embeddings.pkl")

    if not os.path.exists(index_path) or not os.path.exists(metadata_path):
        return None, None, None

    index = faiss.read_index(index_path)
    with open(metadata_path, "rb") as f:
        metadata_data = pickle.load(f)
    with open(embeddings_path, "rb") as f:
        embeddings = pickle.load(f)
    
    return index, metadata_data, embeddings


def add_document_incrementally(file_path, filename):
    index, metadata_data, existing_embeddings = load_existing_index()

    if index is None or metadata_data is None:
        raise Exception("Existing index not found. Please run build_embeddings.py first.")

    raw_text = read_docx(file_path)
    major_issue = extract_major_issue(raw_text, filename)
    chunks = split_subissues(raw_text, major_issue)
    print(f"Adding {len(chunks)} chunks from {filename}")

    new_documents = [chunk["text"] for chunk in chunks]
    new_metadata = [
        {
            "major_issue": chunk["major_issue"],
            "sub_issue": chunk["sub_issue"],
            "source": filename,
        }
        for chunk in chunks
    ]

    new_embeddings = _get_model().encode(new_documents, convert_to_numpy=True)

    # Add to FAISS index
    index.add(np.array(new_embeddings))

    # Update metadata and embeddings
    metadata_data["documents"].extend(new_documents)
    metadata_data["metadata"].extend(new_metadata)
    updated_embeddings = np.vstack((existing_embeddings, new_embeddings))

    # Save everything
    faiss.write_index(index, os.path.join(VECTOR_FOLDER, "nba_index.faiss"))
    with open(os.path.join(VECTOR_FOLDER, "metadata.pkl"), "wb") as f:
        pickle.dump(metadata_data, f)
    with open(os.path.join(VECTOR_FOLDER, "embeddings.pkl"), "wb") as f:
        pickle.dump(updated_embeddings, f)

    return {
        "filename": filename,
        "major_issue": major_issue,
        "chunks_added": len(chunks)
    }


def rebuild_index():
    """Rebuild the entire index from all documents in the documents folder"""
    documents = []
    metadata_list = []

    for filename in os.listdir(DOCUMENT_FOLDER):
        if not filename.endswith(".docx"):
            continue

        print(f"Processing {filename}")
        filepath = os.path.join(DOCUMENT_FOLDER, filename)
        raw_text = read_docx(filepath)
        major_issue = extract_major_issue(raw_text, filename)
        chunks = split_subissues(raw_text, major_issue)
        print(f"{major_issue}: {len(chunks)} chunks")

        for chunk in chunks:
            documents.append(chunk["text"])
            metadata_list.append({
                "major_issue": chunk["major_issue"],
                "sub_issue": chunk["sub_issue"],
                "source": filename,
            })

    print(f"\nTotal Chunks: {len(documents)}")
    print("Generating embeddings...")

    embeddings = _get_model().encode(
        documents,
        convert_to_numpy=True,
        show_progress_bar=True,
    )

    dimension = embeddings.shape[1]
    index = faiss.IndexFlatL2(dimension)
    index.add(np.array(embeddings))

    faiss.write_index(index, os.path.join(VECTOR_FOLDER, "nba_index.faiss"))
    with open(os.path.join(VECTOR_FOLDER, "embeddings.pkl"), "wb") as f:
        pickle.dump(embeddings, f)
    with open(os.path.join(VECTOR_FOLDER, "metadata.pkl"), "wb") as f:
        pickle.dump({
            "model": "all-MiniLM-L6-v2",
            "embedding_dimension": dimension,
            "documents": documents,
            "metadata": metadata_list,
        }, f)

    print("\nEmbeddings rebuilt successfully.")
    return {
        "total_documents": len([f for f in os.listdir(DOCUMENT_FOLDER) if f.endswith(".docx")]),
        "total_chunks": len(documents)
    }


def delete_document(filename):
    """Delete a document from the documents folder and rebuild the index"""
    file_path = os.path.join(DOCUMENT_FOLDER, filename)
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Document {filename} not found")

    os.remove(file_path)
    print(f"Deleted {filename} from documents folder")

    rebuild_result = rebuild_index()
    return {
        "filename": filename,
        "rebuild_result": rebuild_result
    }