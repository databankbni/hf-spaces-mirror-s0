import json
import chromadb

client = chromadb.PersistentClient(path="./heo_db")
collection = client.get_or_create_collection("heo_tips")

with open("heo_tips_full.json", "r", encoding="utf-8") as f:
    tips = json.load(f)

documents = []
metadatas = []
ids = []

for i, tip in enumerate(tips):
    documents.append(tip["tip"])
    metadatas.append({"fault": tip["fault"], "source_video": tip["source_video"]})
    ids.append(f"tip_{i}")

collection.add(
    documents=documents,
    metadatas=metadatas,
    ids=ids
)

print(f"Added {len(tips)} tips to ChromaDB.")
