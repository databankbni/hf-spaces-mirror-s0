from retriever import ComplaintRetriever

retriever = ComplaintRetriever()

query = """
My UPI payment failed and money
was deducted from my account.
"""

results = retriever.search(
    query,
    top_k=20
)

for i, r in enumerate(results):
    print("=" * 80)
    print(f"Result {i+1}")
    print("Complaint ID:", r["complaint_id"])
    print("Product:", r["product"])
    print("Issue:", r["issue"])
    print("Sub Issue:", r["sub_issue"])
    print("Similarity:", r["similarity"])