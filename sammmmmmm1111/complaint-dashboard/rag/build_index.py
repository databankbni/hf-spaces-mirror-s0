# backend/rag/build_index.py

import faiss
import pickle
import numpy as np
from sentence_transformers import SentenceTransformer
from pymongo import MongoClient
from dotenv import load_dotenv
import os

load_dotenv()

MONGODB_URI = os.getenv("MONGODB_URI")
DATABASE_NAME = os.getenv("DATABASE_NAME")

client = MongoClient(MONGODB_URI)
db = client[DATABASE_NAME]

collection = db["complaints"]

model = SentenceTransformer(
    "all-MiniLM-L6-v2"
)

documents = []
metadata = []

complaints = list(collection.find())

for complaint in complaints:

    text = f"""
    Banking Product:
    {complaint.get('product', '')}

    Issue Type:
    {complaint.get('issue', '')}

    Issue Sub Type:
    {complaint.get('sub_issue', '')}

    Customer Complaint:
    {complaint.get('consumer_complaint_narrative', '')}

    Root Cause:
    {complaint.get('root_cause_category', '')}

    Status:
    {complaint.get('status', '')}
    """

    documents.append(text)

    metadata.append(
        {
            "complaint_id":
                complaint.get("complaint_id"),

            "product":
                complaint.get("product"),

            "issue":
                complaint.get("issue"),

            "sub_issue":
                complaint.get("sub_issue"),

            "status":
                complaint.get("status"),

            "root_cause":
                complaint.get("root_cause_category"),

            "text":
                text
        }
    )

embeddings = model.encode(
    documents,
    convert_to_numpy=True,
    show_progress_bar=True
)

dimension = embeddings.shape[1]

index = faiss.IndexFlatL2(
    dimension
)

index.add(
    embeddings.astype("float32")
)

import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

index_path = os.path.join(
    BASE_DIR,
    "complaints.index"
)

metadata_path = os.path.join(
    BASE_DIR,
    "metadata.pkl"
)

faiss.write_index(index, index_path)

with open(metadata_path, "wb") as f:
    pickle.dump(metadata, f)

print(
    f"Indexed {len(metadata)} complaints."
)

print(metadata[0])