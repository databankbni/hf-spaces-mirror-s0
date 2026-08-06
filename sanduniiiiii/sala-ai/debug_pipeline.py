"""
Debug: Trace the full pipeline for a specific query, printing:
1. The exact system prompt sent to the LLM
2. The raw (pre-translation) LLM response
3. Whether get_ai_response returned None/empty or actual text
"""

from dotenv import load_dotenv
load_dotenv()

from chatbot.rag import load_product_db, load_wiki_db, get_product_context, get_wiki_context
from chatbot.prompts import build_system_prompt
from core.model_router import get_ai_response

print("Loading DBs...")
load_product_db()
load_wiki_db()
print()

query = "wifi router ekak thiyenawada"

product_context = get_product_context(query)
wiki_context = get_wiki_context(query)

context_parts = []
if product_context:
    context_parts.append(f"Product information:\n{product_context}")
if wiki_context:
    context_parts.append(f"Wiki / policy information:\n{wiki_context}")
context_text = "\n\n---\n\n".join(context_parts) if context_parts else None

system_prompt = build_system_prompt(context_text, history_text=None)

print("=" * 70)
print("SYSTEM PROMPT SENT TO LLM:")
print("=" * 70)
print(system_prompt)
print()

print("=" * 70)
print(f"USER QUERY: {query}")
print("=" * 70)

reply_en = get_ai_response(prompt=query, system_prompt=system_prompt)

print()
print("=" * 70)
print("RAW LLM RESPONSE (before translation):")
print("=" * 70)
print(repr(reply_en))  # repr() shows None vs empty string vs actual text clearly