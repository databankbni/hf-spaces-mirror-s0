# rag/test_rca.py

from ai_engine import AIEngine
from rag.rca_engine import RCAEngine

ai = AIEngine()
rca = RCAEngine(ai)

result = rca.analyze(
    """
    I made a UPI payment and money
    was deducted but the merchant
    never received it.
    """,
    product="UPI"
)

print(result)