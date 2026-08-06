"""Low-cost business feedback memory for the Agent layer.

Reflections are allowed to improve explanations, evidence ordering, risk hints
and customer copy. They must not override valuation model prices.
"""

from .feedback_schema import FeedbackRecord, ReflectionMemory
from .reflection_generator import generate_reflection
from .reflection_retriever import retrieve_for_context
from .reflection_store import ReflectionStore

__all__ = [
    "FeedbackRecord",
    "ReflectionMemory",
    "ReflectionStore",
    "generate_reflection",
    "retrieve_for_context",
]
