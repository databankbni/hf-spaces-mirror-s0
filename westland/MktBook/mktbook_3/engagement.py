"""
Deal Analytics Engine for mktbook_3: The Agentic Economy

Tracks:
- Semantic agreement tokens (deal closure indicators)
- Persuasion depth (turns to close)
- Circular logic detection (repetitive pitches)
- Red Queen effect (competitive bot dynamics)
- Objection handling (counter-arguments)
- Adaptability (tactical pivots)
"""

import re
from typing import List, Optional, Tuple
from datetime import datetime
from dataclasses import dataclass
from .models import NegotiationContext, CircularLogicDetection, DealState


# Semantic markers for deal closure
AGREEMENT_TOKENS = {
    "accept": ["i accept", "i agree", "sounds good", "i'm in", "let's do it"],
    "deal": ["deal", "it's a deal", "we have a deal", "shaking hands"],
    "confirm": ["confirmed", "locked in", "settled", "finalized"],
    "yes": ["yes", "yeah", "absolutely", "definitely", "for sure"],
}

# Objection phrases (signals of buyer resistance)
OBJECTION_MARKERS = {
    "price": ["too expensive", "too high", "not worth it", "overpriced"],
    "timing": ["not now", "too soon", "not ready", "maybe later"],
    "trust": ["don't trust", "risky", "unsure", "skeptical"],
    "alternative": ["prefer other", "another option", "competitor"],
}

# Repetition patterns (circular logic)
PITCH_PHRASES = {
    "value": ["great value", "best option", "top choice", "unbeatable"],
    "urgency": ["limited time", "act now", "don't miss", "hurry"],
    "pressure": ["take it or leave it", "now or never"],
}


@dataclass
class PersuasionAnalysis:
    """Results from analyzing a negotiation turn."""
    contains_agreement: bool
    agreement_type: Optional[str]  # "accept", "deal", "confirm", "yes"
    
    contains_objection: bool
    objection_type: Optional[str]  # "price", "timing", "trust", "alternative"
    
    is_repetitive_pitch: bool
    pitched_before: bool
    
    is_counter_offer: bool
    counter_count: int
    
    shows_adaptation: bool


class EngagementAnalyzer:
    """Analyzes deal dynamics and persuasion metrics."""
    
    def __init__(self):
        self.conversation_history: dict = {}  # negotiation_id -> list of messages
        self.pitch_inventory: dict = {}  # bot_id -> list of pitches used
    
    def analyze_message(self, negotiation: NegotiationContext, message: str, 
                       speaker: str) -> PersuasionAnalysis:
        """Analyze a single message for deal signals."""
        msg_lower = message.lower()
        
        # Check for agreement tokens
        agreement = self._check_agreement(msg_lower)
        
        # Check for objections
        objection = self._check_objection(msg_lower)
        
        # Check for pitch repetition
        pitch_info = self._check_pitch_repetition(speaker, msg_lower, negotiation)
        
        # Check for counter-offers
        counter_info = self._check_counter_offer(msg_lower)
        
        # Check for adaptation (acknowledging objections)
        adaptation = self._check_adaptation(msg_lower, negotiation, speaker)
        
        return PersuasionAnalysis(
            contains_agreement=agreement[0],
            agreement_type=agreement[1],
            contains_objection=objection[0],
            objection_type=objection[1],
            is_repetitive_pitch=pitch_info[0],
            pitched_before=pitch_info[1],
            is_counter_offer=counter_info[0],
            counter_count=counter_info[1],
            shows_adaptation=adaptation
        )
    
    def _check_agreement(self, msg: str) -> Tuple[bool, Optional[str]]:
        """Scan for semantic agreement tokens."""
        for token_type, phrases in AGREEMENT_TOKENS.items():
            for phrase in phrases:
                if phrase in msg:
                    return (True, token_type)
        return (False, None)
    
    def _check_objection(self, msg: str) -> Tuple[bool, Optional[str]]:
        """Scan for objection markers."""
        for obj_type, phrases in OBJECTION_MARKERS.items():
            for phrase in phrases:
                if phrase in msg:
                    return (True, obj_type)
        return (False, None)
    
    def _check_pitch_repetition(self, speaker: str, msg: str, 
                               negotiation: NegotiationContext) -> Tuple[bool, bool]:
        """Detect if agent is repeating same pitch (circular logic)."""
        if speaker not in self.pitch_inventory:
            self.pitch_inventory[speaker] = []
        
        pitched_before = False
        is_repetitive = False
        
        # Count pitch phrase occurrences
        pitch_count = 0
        for phrase_type, phrases in PITCH_PHRASES.items():
            for phrase in phrases:
                if phrase in msg:
                    pitch_count += 1
                    if phrase in str(self.pitch_inventory[speaker]):
                        pitched_before = True
        
        # If using same phrases repeatedly without progress = circular
        if pitched_before and negotiation.state in [DealState.ENGAGING, DealState.OBJECTION]:
            is_repetitive = True
        
        self.pitch_inventory[speaker].append(msg)
        
        return (is_repetitive, pitched_before)
    
    def _check_counter_offer(self, msg: str) -> Tuple[bool, int]:
        """Detect counter-offers and count them."""
        counter_markers = ["instead", "alternatively", "how about", "what if", 
                          "counter", "revised offer", "new proposal"]
        
        is_counter = any(marker in msg.lower() for marker in counter_markers)
        count = sum(msg.lower().count(marker) for marker in counter_markers)
        
        return (is_counter, count)
    
    def _check_adaptation(self, msg: str, negotiation: NegotiationContext, 
                         speaker: str) -> bool:
        """Detect if agent acknowledges objections and adapts strategy."""
        adaptation_markers = [
            "i understand",
            "i see your point",
            "that's fair",
            "you're right",
            "good point",
            "fair concern",
            "valid objection",
            "acknowledge",
        ]
        
        shows_adaptation = any(marker in msg.lower() for marker in adaptation_markers)
        
        # Also true if agent changes approach after objection
        if negotiation.state == DealState.OBJECTION and len(negotiation.offers) > 1:
            recent_offer = negotiation.offers[-1].offer_text if negotiation.offers else ""
            if recent_offer != msg:  # Changed approach
                shows_adaptation = True
        
        return shows_adaptation
    
    def update_circular_detection(self, negotiation: NegotiationContext):
        """Check if negotiation is stuck in repetitive pattern."""
        if negotiation.turn_count < 4:
            negotiation.circular_logic_flag = CircularLogicDetection.HEALTHY
            return
        
        # Count pitch repetitions in last 5 turns
        recent_offers = negotiation.offers[-5:] if len(negotiation.offers) > 5 else negotiation.offers
        unique_offers = len(set(offer.offer_text for offer in recent_offers))
        
        if len(recent_offers) > 0 and unique_offers <= 1:
            negotiation.circular_logic_flag = CircularLogicDetection.CIRCULAR
        elif len(recent_offers) > 2 and unique_offers <= len(recent_offers) * 0.3:
            negotiation.circular_logic_flag = CircularLogicDetection.WARNING
        else:
            negotiation.circular_logic_flag = CircularLogicDetection.HEALTHY
    
    def calculate_persuasion_depth(self, negotiation: NegotiationContext) -> int:
        """Calculate persuasion depth (turns to close)."""
        if negotiation.is_deal_closed():
            return negotiation.turn_count
        return -1  # No close yet
    
    def calculate_red_queen_score(self, negotiation: NegotiationContext) -> float:
        """
        Calculate Red Queen effect: How many competing bots are in the channel?
        Higher competing count = harder to get attention (lower score).
        """
        if negotiation.competing_bot_count == 0:
            return 1.0  # No competition
        
        # Rank determines multiplier (1st place = 1.0, 2nd = 0.8, etc)
        rank_penalty = max(0.0, 1.0 - (negotiation.attention_rank * 0.15))
        return rank_penalty
    
    def calculate_adaptability_score(self, negotiation: NegotiationContext) -> float:
        """
        Score agent's tactical flexibility (0-1).
        Based on: changing approaches after objections, varied pitches, counter-offers.
        """
        if negotiation.turn_count < 2:
            return 0.5  # Not enough data
        
        # Count unique offers (variety)
        unique_offers = len(set(offer.offer_text for offer in negotiation.offers))
        offer_variety = min(1.0, unique_offers / max(1, negotiation.turn_count / 2))
        
        # Counter-offer frequency
        counter_offers = sum(1 for offer in negotiation.offers 
                            if "alternative" in offer.offer_text.lower() or
                               "different" in offer.offer_text.lower())
        counter_ratio = min(1.0, counter_offers / max(1, negotiation.turn_count / 3))
        
        # Average of variety and counter-offer ratio
        adaptability = (offer_variety + counter_ratio) / 2.0
        
        return adaptability
    
    def get_negotiation_quality(self, negotiation: NegotiationContext) -> dict:
        """Generate comprehensive quality metrics."""
        self.update_circular_detection(negotiation)
        
        return {
            "closed": negotiation.is_deal_closed(),
            "persuasion_depth": self.calculate_persuasion_depth(negotiation),
            "persuasion_efficiency": 1.0 / max(1, negotiation.turn_count * 0.1),
            "circular_logic": negotiation.is_circular_loop(),
            "adaptability": self.calculate_adaptability_score(negotiation),
            "red_queen_score": self.calculate_red_queen_score(negotiation),
            "objections_handled": negotiation.objection_handling,
            "agreement_tokens": negotiation.agreement_tokens,
        }
