import os
import re
import pickle
import numpy as np
import torch
from download_assets import download_assets
from sentence_transformers import SentenceTransformer
from sentence_transformers.util import cos_sim

# -------------------------------------------------
# Paths
# -------------------------------------------------

VECTOR_FOLDER = "nba/vector_store"

METADATA_FILE = os.path.join(
    VECTOR_FOLDER,
    "nba_metadata.pkl",
)

EMBEDDINGS_FILE = os.path.join(
    VECTOR_FOLDER,
    "embeddings.pkl",
)

# -------------------------------------------------
# Lazy-loaded state
# -------------------------------------------------
# Nothing below is loaded at import time. Importing this module (e.g. from
# services.py inside register_complaint()) must be cheap and side-effect
# free. The model, the downloaded assets, and the pickled data are only
# loaded the first time retrieve_nba() is actually called.

_model = None
documents = None
metadata = None
embeddings = None


def _ensure_loaded():
    """Load the embedding model + index data on first use, not on import."""
    global _model, documents, metadata, embeddings

    if _model is not None:
        return

    print("Loading NBA embedding model...")
    _model = SentenceTransformer("all-MiniLM-L6-v2")

    # No-op if files already exist on disk.
    download_assets()

    with open(METADATA_FILE, "rb") as f:
        data = pickle.load(f)

    documents = data["documents"]
    metadata = data["metadata"]

    with open(EMBEDDINGS_FILE, "rb") as f:
        embeddings = pickle.load(f)

    embeddings = np.asarray(embeddings)


# -------------------------------------------------
# Parse Chunk
# -------------------------------------------------

def parse_nba_content(content):

    investigation_steps = []
    next_best_actions = []

    current_section = None

    for line in content.split("\n"):

        line = line.strip()

        if not line:
            continue

        lower = line.lower()

        if "next best actions" in lower:
            current_section = "nba"
            continue

        if "investigation steps" in lower:
            current_section = "investigation"
            continue

        if (
            lower.startswith("major issue")
            or lower.startswith("sub issue")
            or re.match(r"^\d+\.", line)
        ):
            continue

        if current_section == "nba":
            next_best_actions.append(line)

        elif current_section == "investigation":
            investigation_steps.append(line)

    return {
        "investigation_steps": investigation_steps,
        "next_best_actions": next_best_actions,
    }


# -------------------------------------------------
# Retrieve NBA
# -------------------------------------------------
def normalize(text):
    return re.sub(r"\s+", " ", text).strip().lower()

def retrieve_nba(major_issue, sub_issue):

    _ensure_loaded()

    major_issue = major_issue.strip()
    sub_issue = sub_issue.strip()

    if not major_issue or not sub_issue:
        return None

    # ---------------------------------------------
    # Filter only the required Major Issue
    # ---------------------------------------------

    candidate_indices = []
    

    for i, meta in enumerate(metadata):

        if normalize(meta["major_issue"]) == normalize(major_issue):
            candidate_indices.append(i)
    
    print(f"Found {len(candidate_indices)} candidate subissues.")


    if len(candidate_indices) == 0:

        print(f"No NBA document found for major issue: {major_issue}")

        return None
    
    # ---------------------------------------------
    # Exact Sub Issue Match
    # ---------------------------------------------

    for idx in candidate_indices:

        if normalize(metadata[idx]["sub_issue"]) == normalize(sub_issue):

            print("Exact sub issue match found.")

            parsed = parse_nba_content(documents[idx])

            return {
                "major_issue": metadata[idx]["major_issue"],
                "sub_issue": metadata[idx]["sub_issue"],
                "source": metadata[idx]["source"],
                "similarity_score": 1.0,
                "investigation_steps": parsed["investigation_steps"],
                "next_best_actions": parsed["next_best_actions"],
            }

    # ---------------------------------------------
    # Encode Query
    # ---------------------------------------------

    query = f"{major_issue} {sub_issue}"

    query_embedding = _model.encode(
        [query],
        convert_to_numpy=True,
    )[0]

    candidate_vectors = embeddings[candidate_indices]

    scores = cos_sim(
        torch.tensor(query_embedding),
        torch.tensor(candidate_vectors),
    )[0]

    best_local_index = int(torch.argmax(scores))

    best_global_index = candidate_indices[best_local_index]

    # -------------------------------
    # Confidence Threshold
    # -------------------------------

    best_score = float(scores[best_local_index])

    if best_score < 0.55:
        print(
            f"No confident NBA match found. Best score: {best_score:.3f}"
        )
        return None

    parsed = parse_nba_content(
        documents[best_global_index]
    )
    
    print("\n========== NBA SEARCH ==========")
    print(f"Major Issue : {major_issue}")
    print(f"Sub Issue   : {sub_issue}")
    print(f"Candidates  : {len(candidate_indices)}")
    print(f"Retrieved   : {metadata[best_global_index]['sub_issue']}")
    print(f"Similarity  : {best_score:.3f}")
    print("================================\n")

    return {
        "major_issue": metadata[best_global_index]["major_issue"],
        "sub_issue": metadata[best_global_index]["sub_issue"],
        "source": metadata[best_global_index]["source"],
        "similarity_score": best_score,
        "investigation_steps": parsed["investigation_steps"],
        "next_best_actions": parsed["next_best_actions"],
    }


# -------------------------------------------------
# Testing
# -------------------------------------------------

if __name__ == "__main__":

    result = retrieve_nba(
        major_issue="Credit Card",
        sub_issue="Unauthorized Transaction",
    )

    from pprint import pprint

    pprint(result)