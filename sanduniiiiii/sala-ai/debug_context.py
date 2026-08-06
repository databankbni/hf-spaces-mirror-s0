"""
Debug: Check what context is actually being retrieved and sent to the LLM
for a specific query.
"""

from dotenv import load_dotenv
load_dotenv()

from chatbot.rag import load_product_db, get_product_context

# Must load the DB first - this normally happens at FastAPI startup
print("Loading product DB...")
load_product_db()
print()

query = "wifi router ekak thiyenawada"
context = get_product_context(query)

print("=" * 60)
print(f"QUERY: {query}")
print("=" * 60)

if context is None:
    print("No context retrieved (retriever returned nothing)")
else:
    print(f"Context length: {len(context)} characters\n")
    print(context)