# backend/rag/retriever.py

import faiss
import pickle
import numpy as np
from sentence_transformers import SentenceTransformer
from pymongo import MongoClient
from dotenv import load_dotenv
import os

load_dotenv()

class ComplaintRetriever:
    def __init__(self):
        self.model = SentenceTransformer(
            "all-MiniLM-L6-v2"
        )
        self.index = faiss.IndexFlatL2(384)
        self.metadata = []
        
    def _get_mongo_client(self):
        mongodb_uri = os.getenv("MONGODB_URI")
        return MongoClient(mongodb_uri)
    
    def load_from_mongodb(self):
        """Load all complaints from MongoDB and build the index"""
        client = self._get_mongo_client()
        db = client[os.getenv("DATABASE_NAME")]
        collection = db["complaints"]
        
        complaints = list(collection.find())
        
        documents = []
        self.metadata = []
        
        for complaint in complaints:
            text = f"""
Banking Product: {complaint.get('product', '')}
Issue Type: {complaint.get('issue', '')}
Issue Sub Type: {complaint.get('sub_issue', '')}
Customer Complaint: {complaint.get('consumer_complaint_narrative', '')}
Root Cause: {complaint.get('root_cause_category', '')}
Status: {complaint.get('status', '')}
"""
            documents.append(text)
            
            self.metadata.append({
                "complaint_id": complaint.get("complaint_id"),
                "product": complaint.get("product"),
                "issue": complaint.get("issue"),
                "sub_issue": complaint.get("sub_issue"),
                "status": complaint.get("status"),
                "root_cause": complaint.get("root_cause_category"),
                "text": text
            })
        
        if documents:
            embeddings = self.model.encode(
                documents,
                convert_to_numpy=True
            )
            self.index.add(embeddings.astype("float32"))
        
        print(f"✅ Loaded {len(complaints)} complaints into RAG index from MongoDB!")
    
    def add_complaint(self, complaint):
        """Add a single complaint to the index incrementally"""
        text = f"""
Banking Product: {complaint.get('product', '')}
Issue Type: {complaint.get('issue', '')}
Issue Sub Type: {complaint.get('sub_issue', '')}
Customer Complaint: {complaint.get('consumer_complaint_narrative', '')}
Root Cause: {complaint.get('root_cause_category', '')}
Status: {complaint.get('status', '')}
"""
        embedding = self.model.encode([text], convert_to_numpy=True)
        self.index.add(embedding.astype("float32"))
        
        self.metadata.append({
            "complaint_id": complaint.get("complaint_id"),
            "product": complaint.get("product"),
            "issue": complaint.get("issue"),
            "sub_issue": complaint.get("sub_issue"),
            "status": complaint.get("status"),
            "root_cause": complaint.get("root_cause_category"),
            "text": text
        })
        
        print(f"✅ Added complaint {complaint.get('complaint_id')} to RAG index!")

    def search(
        self,
        query,
        top_k=5,
        product=None,
        issue=None
    ):
        query_embedding = self.model.encode(
            [query],
            convert_to_numpy=True
        )

        D, I = self.index.search(
            query_embedding.astype("float32"),
            top_k * 5
        )

        results = []
        seen_ids = set()

        for score, idx in zip(D[0], I[0]):
            if idx == -1:
                continue

            complaint_meta = self.metadata[idx]

            if (
                product
                and complaint_meta["product"] != product
            ):
                continue

            if (
                issue
                and complaint_meta["issue"] != issue
            ):
                continue

            complaint_id = complaint_meta["complaint_id"]

            if complaint_id in seen_ids:
                continue

            seen_ids.add(complaint_id)

            result = complaint_meta.copy()

            result["similarity"] = (
                1 / (1 + float(score))
            )

            results.append(result)

            if len(results) >= top_k:
                break

        return results