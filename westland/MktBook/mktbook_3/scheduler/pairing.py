"""
Pairing Strategies for mktbook_3 Negotiations

Determines which two bots should negotiate together.
Strategies:
- Random: Random pairing
- RedQueen: Rank bots by win rate, force stronger bots to compete
- DiversePersona: Pair different personas together
"""

import random
from typing import Tuple, Optional, List, Any
from abc import ABC, abstractmethod


class PairingStrategy(ABC):
    """Base class for bot pairing strategies."""
    
    @abstractmethod
    def select_pair(self, bots: List[Any]) -> Tuple[Optional[Any], Optional[Any]]:
        """Select two bots to negotiate."""
        pass


class RandomPairing(PairingStrategy):
    """Randomly select any two bots."""
    
    def select_pair(self, bots: List[Any]) -> Tuple[Optional[Any], Optional[Any]]:
        """Select two random bots."""
        if len(bots) < 2:
            return None, None
        
        selected = random.sample(bots, 2)
        return selected[0], selected[1]


class RedQueenPairing(PairingStrategy):
    """
    Red Queen effect: Prioritize pairings between high-performing bots.
    Forces competitive dynamics where strong bots compete against each other.
    """
    
    def select_pair(self, bots: List[Any]) -> Tuple[Optional[Any], Optional[Any]]:
        """Select bots with Red Queen strategy."""
        if len(bots) < 2:
            return None, None
        
        # Sort by win rate (descending) - strongest bots first
        sorted_bots = sorted(
            bots, 
            key=lambda b: self._get_bot_score(b), 
            reverse=True
        )
        
        # Select from top performers with weighted probability
        # Top bot always selected
        initiator = sorted_bots[0]
        
        # Responder selected with bias toward other strong bots
        responder_weights = self._calculate_weights(sorted_bots[1:])
        responder = random.choices(sorted_bots[1:], weights=responder_weights, k=1)[0]
        
        return initiator, responder
    
    def _get_bot_score(self, bot) -> float:
        """Score bot for pairing priority."""
        profile = getattr(bot, 'profile', None)
        if not profile:
            return 0.5
        
        # Use win rate as primary score
        return profile.win_rate if hasattr(profile, 'win_rate') else 0.5
    
    def _calculate_weights(self, bots: List[Any]) -> List[float]:
        """Calculate pairing weights for bots (higher = more likely)."""
        scores = [self._get_bot_score(b) for b in bots]
        total = sum(scores)
        
        if total == 0:
            return [1.0 / len(bots)] * len(bots)
        
        return [s / total for s in scores]


class DiversePersonaPairing(PairingStrategy):
    """
    Pair bots with different personas.
    Ensures Arbitrage pairs with Outreach/Intelligence, etc.
    """
    
    def select_pair(self, bots: List[Any]) -> Tuple[Optional[Any], Optional[Any]]:
        """Select bots with different personas."""
        if len(bots) < 2:
            return None, None
        
        # Pick first bot randomly
        initiator = random.choice(bots)
        
        # Find bots with different persona
        different_persona = [
            b for b in bots 
            if b != initiator and b.persona != initiator.persona
        ]
        
        if not different_persona:
            # Fall back to random if no persona diversity available
            different_persona = [b for b in bots if b != initiator]
        
        if not different_persona:
            return None, None
        
        responder = random.choice(different_persona)
        
        return initiator, responder


class BalancedPairingStrategy(PairingStrategy):
    """
    Balanced approach: Mix of Red Queen competition and diverse personas.
    - 60% probability: Red Queen (force competition)
    - 40% probability: Diverse Persona (varied matchups)
    """
    
    def __init__(self):
        self.red_queen = RedQueenPairing()
        self.diverse_persona = DiversePersonaPairing()
    
    def select_pair(self, bots: List[Any]) -> Tuple[Optional[Any], Optional[Any]]:
        """Select pair using mixed strategy."""
        if len(bots) < 2:
            return None, None
        
        # Choose strategy with probability
        if random.random() < 0.6:
            return self.red_queen.select_pair(bots)
        else:
            return self.diverse_persona.select_pair(bots)
