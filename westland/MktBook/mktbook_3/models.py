"""
Negotiation Models for mktbook_3: The Agentic Economy

Workout #3 focuses on agent-to-agent hard selling, deal-closing, and negotiation.
Personas represent different selling strategies: Arbitrage, Outreach, Intelligence.

Deal Success Criteria:
- Semantic agreement tokens ("I accept", "deal", "agreed", etc.)
- Persuasion depth (number of turns to close)
- Red Queen effect (competing with other bots for attention)
- Circular logic detection (avoiding repetitive pitches)
"""

from enum import Enum
from dataclasses import dataclass, field
from typing import Optional, List
from datetime import datetime


class NegotiationPersona(str, Enum):
    """Three core personas for mktbook_3 negotiation strategies."""
    ARBITRAGE = "arbitrage"      # Exploits price gaps and market inefficiencies
    OUTREACH = "outreach"        # Cold-calling and direct sales approach
    INTELLIGENCE = "intelligence" # Data gathering and market research


class DealState(str, Enum):
    """Stages of deal progression."""
    INITIATED = "initiated"      # First contact made
    ENGAGING = "engaging"        # Back-and-forth negotiation
    OBJECTION = "objection"      # Objection raised by counter-party
    COUNTER_OFFERED = "counter_offered"  # Alternative proposal made
    NEAR_CLOSE = "near_close"    # Signals of agreement appearing
    CLOSED = "closed"            # Deal confirmed with semantic agreement token
    STALLED = "stalled"          # No progress for N turns
    ABANDONED = "abandoned"      # Conversation ended without deal


class CircularLogicDetection(str, Enum):
    """Detection of repetitive/stuck negotiation patterns."""
    HEALTHY = "healthy"          # Adaptive, responsive negotiation
    WARNING = "warning"          # Some repetition detected
    CIRCULAR = "circular"        # Agent repeating same pitch (fails grading)


@dataclass
class DealOffer:
    """Represents a specific offer in a negotiation."""
    offer_id: str
    actor: str                    # Bot ID making offer
    offer_text: str              # The actual offer
    value: float                 # Quantified offer value
    timestamp: datetime          # When offer was made
    response_count: int = 0      # How many responses to this offer
    accepted: bool = False       # Did counterparty accept?


@dataclass
class NegotiationContext:
    """Full context of an active negotiation between two agents."""
    negotiation_id: str
    initiator: str               # Bot ID that started
    responder: str               # Bot ID responding
    initiator_persona: NegotiationPersona
    responder_persona: NegotiationPersona
    
    # Negotiation state
    state: DealState = DealState.INITIATED
    offers: List[DealOffer] = field(default_factory=list)
    turn_count: int = 0
    agreement_tokens: List[str] = field(default_factory=list)  # "I accept", "deal", etc.
    
    # Metrics
    persuasion_depth: int = 0    # Turns to close (lower = better)
    adaptability_score: float = 0.5  # 0-1: Does agent adapt strategy?
    circular_logic_flag: CircularLogicDetection = CircularLogicDetection.HEALTHY
    objection_handling: int = 0  # Count of objections successfully countered
    
    # Red Queen effect
    competing_bot_count: int = 0 # How many other bots in same channel
    attention_rank: int = 0      # Position in channel noise (1=best)
    
    # Timing
    started_at: datetime = field(default_factory=datetime.now)
    last_activity: datetime = field(default_factory=datetime.now)
    closed_at: Optional[datetime] = None
    
    def is_deal_closed(self) -> bool:
        """Check if semantic agreement found."""
        return self.state == DealState.CLOSED and len(self.agreement_tokens) > 0
    
    def is_circular_loop(self) -> bool:
        """Returns True if agent stuck in repetitive pattern."""
        return self.circular_logic_flag == CircularLogicDetection.CIRCULAR
    
    def mark_deal_closed(self, agreement_token: str):
        """Record successful deal close with semantic token."""
        self.state = DealState.CLOSED
        self.agreement_tokens.append(agreement_token)
        self.closed_at = datetime.now()
        self.persuasion_depth = self.turn_count
    
    def close_stalled(self):
        """Mark negotiation as stalled (no deal)."""
        self.state = DealState.STALLED
        self.closed_at = datetime.now()


@dataclass
class BotProfile:
    """Extended bot profile for mktbook_3 with negotiation capabilities."""
    bot_id: str
    bot_name: str
    persona: NegotiationPersona
    
    # Sales stats
    total_deals: int = 0
    closed_deals: int = 0        # Successful closes
    stalled_deals: int = 0       # No deal reached
    
    # Performance metrics
    win_rate: float = 0.0        # closed_deals / (closed_deals + stalled_deals)
    avg_persuasion_depth: float = 0.0  # Avg turns to close
    adaptability: float = 0.5    # How well does it adjust tactics?
    circular_logic_incidents: int = 0  # Times caught in circular pattern
    
    # Red Queen tracking
    attention_battles_won: int = 0  # Outbid competitors in same channel
    
    # Chain-of-thought depth
    reasoning_depth: float = 0.5 # Does it think before speaking?
    
    def calculate_win_rate(self):
        """Recalculate win rate from deal counts."""
        total = self.closed_deals + self.stalled_deals
        if total > 0:
            self.win_rate = self.closed_deals / total
        return self.win_rate


@dataclass
class GradeMetrics:
    """Final grading metrics for mktbook_3."""
    bot_id: str
    total_negotiations: int
    successful_closes: int
    
    # Weighted components (Workout #3 grading)
    deal_conversion_score: float  # 40% weight - Primary metric
    persuasion_depth_score: float # 25% weight - Efficiency of close
    adaptability_score: float     # 20% weight - Tactical adjustment
    logic_health_score: float     # 15% weight - Avoid circular patterns
    
    final_grade: float = 0.0      # 0-100
    
    def calculate_final_grade(self) -> float:
        """Weighted calculation: Conversion is primary, logic is penalty."""
        base = (
            self.deal_conversion_score * 0.40 +
            self.persuasion_depth_score * 0.25 +
            self.adaptability_score * 0.20 +
            self.logic_health_score * 0.15
        )
        self.final_grade = base
        return self.final_grade
