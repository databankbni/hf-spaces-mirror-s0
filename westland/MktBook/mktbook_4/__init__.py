"""mktbook_4: Synthetic Studio Economy — per-student DB-driven fashion bots."""
__version__ = "0.96.0"
from .bots.fleet import BotFleet
from .bots.bot_client import SingleBot
from .scheduler.loop import TrendScheduler
__all__ = ["BotFleet", "SingleBot", "TrendScheduler"]
