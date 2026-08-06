"""mktbook_3: The Agentic Economy — per-student DB-driven negotiation bots."""

__version__ = "0.96.0"

from .models import (
    NegotiationPersona,
    DealState,
    NegotiationContext,
    BotProfile,
    GradeMetrics,
)
from .bots.fleet import BotFleet
from .bots.bot_client import SingleBot
from .scheduler.loop import NegotiationScheduler
from .grading.evaluator import DealEvaluator

__all__ = [
    "NegotiationPersona",
    "DealState",
    "NegotiationContext",
    "BotProfile",
    "GradeMetrics",
    "BotFleet",
    "SingleBot",
    "NegotiationScheduler",
    "DealEvaluator",
]
