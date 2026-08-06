import os
import re
import pickle
from docx import Document
from sentence_transformers import SentenceTransformer
import faiss
import numpy as np

# -----------------------------
# Paths
# -----------------------------
DOCUMENT_FOLDER = "nba/documents"
VECTOR_FOLDER = "nba/vector_store"

os.makedirs(VECTOR_FOLDER, exist_ok=True)

# -----------------------------
# Load embedding model
# -----------------------------
print("Loading embedding model...")

model = SentenceTransformer("all-MiniLM-L6-v2")

# -----------------------------
# Storage
# -----------------------------
documents = []
metadata = []


def read_docx(file_path):
    """Read complete text from a Word document."""
    doc = Document(file_path)

    text = []
    for para in doc.paragraphs:
        if para.text.strip():
            text.append(para.text.strip())

    return "\n".join(text)


def extract_major_issue(text, filename):
    """
    Extract Major Issue from the document.
    Falls back to filename if heading is missing.
    """

    lines = [line.strip() for line in text.split("\n") if line.strip()]

    if lines:
        match = re.search(
            r"Major\s+Issue\s*:\s*(.*)",
            lines[0],
            re.IGNORECASE,
        )

        if match:
            return match.group(1).strip()

    # Fallback to filename
    name = filename.replace(".docx", "")
    name = re.sub(r"Major\s*Issue[_ ]*", "", name, flags=re.IGNORECASE)
    name = name.replace("_", " ").strip()

    return name

def split_subissues(text, major_issue):
    """
    Splits using

    1.
    2.
    3.
    ...

    """

    # remove major issue line
    text = re.sub(
    r"Major\s+Issue\s*:\s*.*?\n",
    "",
    text,
    count=1,
    flags=re.IGNORECASE,
)

    # split at numbered complaints
    parts = re.split(r"\n(?=\d+\.?\s+)", text)

    chunks = []

    for part in parts:

        part = part.strip()

        if not part:
            continue

        # extract complaint name

        first_line = part.split("\n")[0]

        complaint = re.sub(r"^\d+\.?\s*", "", first_line)
        complaint = re.sub(r"\s+", " ", complaint).strip()

        final_chunk = f"""
Major Issue: {major_issue}

Sub Issue: {complaint}

{part}
"""

        chunks.append(
            {
                "text": final_chunk,
                "major_issue": major_issue,
                "sub_issue": complaint,
            }
        )

    return chunks


# -----------------------------
# Process every document
# -----------------------------

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

        metadata.append(
            {
                "major_issue": chunk["major_issue"],
                "sub_issue": chunk["sub_issue"],
                "source": filename,
            }
        )

print(f"\nTotal Chunks: {len(documents)}")

# -----------------------------
# Generate embeddings
# -----------------------------

print("Generating embeddings...")

embeddings = model.encode(
    documents,
    convert_to_numpy=True,
    show_progress_bar=True,
)
with open(
    os.path.join(VECTOR_FOLDER, "embeddings.pkl"),
    "wb",
) as f:
    pickle.dump(embeddings, f)
# -----------------------------
# Build FAISS
# -----------------------------

dimension = embeddings.shape[1]

index = faiss.IndexFlatL2(dimension)

index.add(np.array(embeddings))

# -----------------------------
# Save
# -----------------------------

faiss.write_index(
    index,
    os.path.join(VECTOR_FOLDER, "nba_index.faiss"),
)

with open(
    os.path.join(VECTOR_FOLDER, "metadata.pkl"),
    "wb",
) as f:
    pickle.dump(
{
    "model": "all-MiniLM-L6-v2",
    "embedding_dimension": dimension,
    "documents": documents,
    "metadata": metadata,
},
f,
)

print("\nEmbeddings saved successfully.")
print(f"Stored {len(documents)} complaint chunks.")
print("\nFirst metadata:")
print(metadata[0])

print("\nFirst chunk:")
print(documents[0])