"""mktbook_5: Bayesian Showdown — per-student DB-driven A/B marketing bots."""
__version__ = "0.96.0"
from .bots.fleet import BotFleet
from .bots.marketing_bots import SingleBot
__all__ = ["BotFleet", "SingleBot"]
