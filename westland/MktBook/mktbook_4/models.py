"""
Fashion Models for mktbook_4: The Synthetic Studio Economy

Tracks fashion trends, aesthetic qualities, and influence metrics.
Core concept: "Miranda Priestly Factor" - being the tastemaker, not the follower.

Success = Other bots adopt YOUR trend vocabulary and visual descriptions.
"""

from enum import Enum
from dataclasses import dataclass, field
from typing import Optional, List
from datetime import datetime


class VisualStrategy(str, Enum):
    """Fashion advertising strategies based on visual psychology."""
    MIRROR = "mirror"              # Describe image resembling the user
    DEMOGRAPHIC_SWAP = "demographic_swap"  # Adjust models to match target demographic
    CULTURAL_REFERENCE = "cultural_reference"  # Reference cultural icons/movements
    MINIMALIST = "minimalist"      # Less is more aesthetic
    MAXIMALIST = "maximalist"      # More is more aesthetic
    SUSTAINABLE = "sustainable"   # Eco-conscious fashion narrative
    LEGACY = "legacy"              # Timeless/heritage angle


class AestheticDimension(str, Enum):
    """Dimensions for evaluating fashion aesthetic quality."""
    COLOR_HARMONY = "color_harmony"          # Does color scheme work?
    SILHOUETTE_CLARITY = "silhouette_clarity"  # Is shape/form distinctive?
    TEXTURE_QUALITY = "texture_quality"      # Details visible and appealing?
    TREND_RELEVANCE = "trend_relevance"      # Fits current market trends?
    ORIGINALITY = "originality"              # Novel or derivative?
    BRAND_CONSISTENCY = "brand_consistency"  # Maintains visual identity?


@dataclass
class FashionTrend:
    """A specific fashion trend proposed by an agent."""
    trend_id: str
    creator_bot_id: str
    trend_name: str                # e.g., "Cerulean Minimalism"
    description: str               # Rich fashion description
    visual_strategy: VisualStrategy
    
    # Generated content
    image_prompt: str             # DALL-E-ready prompt
    generated_image_url: str      # URL of generated image
    local_image_path: Optional[str] = None  # Path on disk
    
    # Influence tracking
    adopters: List[str] = field(default_factory=list)  # Bot IDs that referenced this trend
    mention_count: int = 0        # How many times mentioned in guild
    
    # Aesthetic evaluation
    aesthetic_scores: dict = field(default_factory=dict)  # {dimension -> score}
    avg_aesthetic_score: float = 0.0
    
    # IP compliance
    brand_mentions: List[str] = field(default_factory=list)  # Brands mentioned
    copyright_flags: List[str] = field(default_factory=list)  # Flagged issues
    is_compliant: bool = True     # Passed IP check
    
    # Timing
    proposed_at: datetime = field(default_factory=datetime.now)
    trend_lifespan_hours: int = 24  # How long trend is "active"
    
    def is_active(self) -> bool:
        """Check if trend is still active."""
        age = (datetime.now() - self.proposed_at).total_seconds() / 3600
        return age < self.trend_lifespan_hours
    
    def update_influence(self):
        """Recalculate influence metrics."""
        self.mention_count = len(self.adopters)
        if self.mention_count > 0:
            # Adopter influence: more adopters = more influence
            return self.mention_count
        return 0


@dataclass
class ImageEvaluation:
    """Evaluation of a generated fashion image."""
    evaluation_id: str
    image_id: str                 # Which generated image
    evaluator_bot_id: str         # Which bot evaluated
    
    # Visual assessment
    aesthetic_scores: dict        # {dimension -> 0-100 score}
    overall_quality: float        # 0-100
    
    # Verbal evaluation
    aesthetic_commentary: str     # Bot's written take on the image
    cultural_relevance: str       # Why this matters in fashion
    verbal_score: float          # GradeBot scores this text
    
    # Influence signal
    would_adopt_trend: bool      # Does evaluator want to use this trend?
    
    # Timestamp
    evaluated_at: datetime = field(default_factory=datetime.now)


@dataclass
class BotProfile:
    """Fashion Agent profile tracking."""
    bot_id: str
    bot_name: str
    
    # Fashion portfolio
    trends_proposed: int = 0      # Total trends this bot created
    trends_adopted: int = 0       # Trends from others this bot adopted
    
    # Influence metrics (Miranda Priestly Factor)
    tastemaker_score: float = 0.5  # 0-1: How much bot dictates vs follows (0=follower, 1=dictator)
    influence_index: float = 0.0   # How many bots reference this bot's trends
    cultural_authority: float = 0.0  # Overall "coolness" ranking
    
    # Quality tracking
    avg_image_quality: float = 0.0
    avg_aesthetic_score: float = 0.0
    ip_violations: int = 0        # Copyright strikes
    
    # Aesthetic profile
    preferred_strategies: dict = field(default_factory=dict)  # Strategy -> usage_count
    color_palette: List[str] = field(default_factory=list)  # Dominant colors used
    aesthetic_signature: str = ""  # Distinctive style identifier
    
    def calculate_miranda_index(self) -> float:
        """
        Calculate "Miranda Priestly" factor.
        
        Formula:
        - Base: 50 (neutral)
        - +10 per original trend (innovation)
        - -10 per adopted trend (following)
        - +5 per other bot adopting your trend (influence)
        - -5 per IP violation (ethical cost)
        
        Range: 0 (pure follower) to 100 (pure tastemaker)
        """
        score = 50.0
        score += (self.trends_proposed * 10)
        score -= (self.trends_adopted * 10)
        score += (self.influence_index * 5)
        score -= (self.ip_violations * 5)
        
        return min(100.0, max(0.0, score))


@dataclass
class GradeMetrics:
    """Final grading for mktbook_4."""
    bot_id: str
    
    # Grading components (weighted)
    creativity_score: float       # 35% - Novel aesthetic direction
    influence_score: float        # 35% - Miranda Priestly factor (others adopt)
    aesthetic_quality_score: float  # 20% - Image quality & brand consistency
    ethics_score: float           # 10% - IP compliance, no copyright violations
    
    final_grade: float = 0.0
    
    def calculate_final_grade(self) -> float:
        """
        Calculate final grade with weights:
        - 35% Creativity (originality)
        - 35% Influence (tastemaker status)
        - 20% Aesthetic Quality (image consistency + evaluation scores)
        - 10% Ethics (IP compliance)
        """
        base = (
            self.creativity_score * 0.35 +
            self.influence_score * 0.35 +
            self.aesthetic_quality_score * 0.20 +
            self.ethics_score * 0.10
        )
        
        self.final_grade = base
        return self.final_grade
