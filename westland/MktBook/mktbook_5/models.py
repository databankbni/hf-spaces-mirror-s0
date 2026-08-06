"""
Data Models for mktbook_5: Bayesian A/B Testing Framework

Core structures for:
- Marketing strategies (Aggressive vs. Passive, Visual vs. Textual)
- A/B ecosystem tracking
- Engagement metrics
- Performance comparison
- Bayesian priors/posteriors
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Tuple
from datetime import datetime


class StrategyType(Enum):
    """Marketing strategy dimensions."""
    AGGRESSIVE = "aggressive"  # Hard sell, direct CTA
    PASSIVE = "passive"        # Soft touch, relationship-based
    VISUAL = "visual"          # Image/video-driven
    TEXTUAL = "textual"        # Narrative/wit-driven
    TECHNICAL = "technical"    # spec-focused, data-driven
    EMOTIONAL = "emotional"    # Story-driven, connection-focused


class EcosystemLabel(Enum):
    """Ecosystem A or B designation."""
    ECOSYSTEM_A = "A"
    ECOSYSTEM_B = "B"


@dataclass
class MarketingStrategy:
    """Defines a bot's marketing approach."""
    name: str                              # e.g., "Aggressive Visuals"
    primary_strategy: StrategyType        # Main axis
    secondary_strategy: Optional[StrategyType]  # Secondary axis
    hypothesis: str                        # Why this will win
    target_audience: str                   # Demo, psychographics
    value_proposition: str                 # Core message
    engagement_prediction: float           # 0-100: expected engagement
    conversion_prediction: float           # 0-100: expected conversions


@dataclass
class ProductListing:
    """Product/service being marketed."""
    product_id: str
    name: str
    description: str
    price: float
    category: str
    brand: str
    unique_selling_points: List[str]
    discount_available: bool
    discount_percent: Optional[float] = None


@dataclass
class BotInteraction:
    """Single bot interaction with a user."""
    interaction_id: str
    bot_name: str
    ecosystem: EcosystemLabel
    timestamp: datetime
    user_id: str
    message_content: str
    product_shown: Optional[str]
    engagement_type: str              # "view", "click", "inquire", "buy"
    sentiment_score: float            # -1 to 1
    user_reaction: Optional[str]      # emoji or feedback


@dataclass
class EngagementMetrics:
    """Session-level engagement data."""
    session_id: str
    bot_name: str
    ecosystem: EcosystemLabel
    metric_timestamp: datetime
    
    # Event counts
    impressions: int = 0              # Users saw content
    clicks: int = 0                   # Clicked on CTA
    inquiries: int = 0                # Asked questions
    conversions: int = 0              # Made purchase
    cart_abandons: int = 0            # Left without buying
    
    # Derived metrics
    engagement_rate: float = 0.0      # Clicks / Impressions
    conversion_rate: float = 0.0      # Conversions / Impressions
    average_sentiment: float = 0.0    # Average sentiment score
    bounce_rate: float = 0.0          # % left without action
    
    # Revenue metrics
    revenue_generated: float = 0.0
    customer_lifetime_value: float = 0.0
    
    def calculate_engagement_score(self) -> float:
        """Derive composite engagement score (0-100)."""
        if self.impressions == 0:
            return 0.0
        
        engagement = (
            (self.clicks / self.impressions) * 25 +           # CTR: 25%
            (self.conversions / self.impressions) * 50 +       # Conversion: 50%
            ((self.average_sentiment + 1) / 2) * 25           # Sentiment: 25%
        ) * 100
        
        return min(100.0, engagement)


@dataclass
class BayesianObservation:
    """Single observation for Bayesian updating."""
    observation_id: str
    ecosystem: EcosystemLabel
    bot_name: str
    timestamp: datetime
    metric_type: str                  # "engagement", "conversion", "sentiment"
    observed_value: float             # The actual measurement
    variance: float                   # Confidence/uncertainty


@dataclass
class BayesianPosterior:
    """Posterior distribution estimates (Westland's framework)."""
    ecosystem: EcosystemLabel
    bot_name: str
    metric_type: str
    
    # Posterior estimates
    posterior_mean: float
    posterior_variance: float
    posterior_std: float              # √variance
    credible_interval_lower: float    # 95% CI
    credible_interval_upper: float
    
    # Prior info (for traceability)
    prior_mean: float
    prior_variance: float
    
    # Observations used
    observation_count: int
    update_timestamp: datetime
    
    def effective_sample_size(self) -> float:
        """Estimate effective sample size from variance reduction."""
        if self.prior_variance == 0:
            return float(self.observation_count)
        return 1.0 + (self.prior_variance / self.posterior_variance)


@dataclass
class ComparisonResult:
    """A/B test comparison between two ecosystems."""
    comparison_id: str
    test_metric: str                  # "engagement", "conversion", "revenue"
    ecosystem_a: EcosystemLabel       # Winner or control
    ecosystem_b: EcosystemLabel       # Challenger or treatment
    
    # Statistical results
    mean_diff: float                  # A - B
    effect_size: float                # Cohen's d
    t_statistic: float
    p_value: float                    # Significance
    credible_interval: Tuple[float, float]  # Bayesian CI
    
    # Practical significance
    probability_a_better: float       # P(A > B | data)
    probability_b_better: float       # P(B > A | data)
    probability_equivalent: float     # P(A ≈ B | data)
    
    # Recommendation
    recommendation: str               # "Scale A", "Scale B", "Continue Testing", etc.
    confidence_level: float           # 0-1
    comparison_timestamp: datetime
    
    def is_significant(self, threshold: float = 0.05) -> bool:
        """Check statistical significance."""
        return self.p_value < threshold


@dataclass
class ValueScore:
    """Aggregated value metric for ecosystem.
    
    Combines engagement, conversion, revenue, and influence.
    """
    ecosystem: EcosystemLabel
    bot_name: str
    score_timestamp: datetime
    
    # Component scores (0-100)
    engagement_component: float    # % of engagements achieved
    conversion_component: float    # % of conversions
    revenue_component: float       # Revenue per user compared to target
    influence_component: float     # Social/word-of-mouth potential
    
    # Weighted total
    total_value_score: float       # Final 0-100 score
    weights: Dict[str, float] = field(default_factory=lambda: {
        "engagement": 0.25,
        "conversion": 0.35,
        "revenue": 0.30,
        "influence": 0.10
    })
    
    def calculate_total(self) -> float:
        """Recalculate weighted total."""
        self.total_value_score = (
            (self.engagement_component * self.weights["engagement"]) +
            (self.conversion_component * self.weights["conversion"]) +
            (self.revenue_component * self.weights["revenue"]) +
            (self.influence_component * self.weights["influence"])
        )
        return self.total_value_score


@dataclass
class PerformanceTrajectory:
    """Tracks improvement slope over time.
    
    For comparing: Does Strategy A improve faster than Strategy B?
    """
    ecosystem: EcosystemLabel
    bot_name: str
    metric_type: str                 # "engagement", "conversion", etc.
    
    # Observations over time (in order)
    timestamps: List[datetime] = field(default_factory=list)
    values: List[float] = field(default_factory=list)
    
    # Derived trajectory
    slope: float = 0.0               # Improvement rate (value/hour)
    intercept: float = 0.0
    r_squared: float = 0.0           # Fit quality
    
    # Predictions
    projected_value_24h: float = 0.0
    projected_value_7d: float = 0.0
    
    def fit_trajectory(self) -> None:
        """Fit linear regression to data."""
        if len(self.values) < 2:
            return
        
        import numpy as np
        x = np.arange(len(self.values))
        y = np.array(self.values)
        
        coeffs = np.polyfit(x, y, 1)
        self.slope = float(coeffs[0])
        self.intercept = float(coeffs[1])
        
        # Calculate R²
        y_pred = np.polyval(coeffs, x)
        ss_res = np.sum((y - y_pred) ** 2)
        ss_tot = np.sum((y - np.mean(y)) ** 2)
        if ss_tot != 0:
            self.r_squared = float(1 - (ss_res / ss_tot))
    
    def add_observation(self, timestamp: datetime, value: float) -> None:
        """Add new observation and update trajectory."""
        self.timestamps.append(timestamp)
        self.values.append(value)
        self.fit_trajectory()
        
        # Project ahead
        if len(self.values) >= 2:
            self.projected_value_24h = self.intercept + self.slope * (len(self.values) + 24)
            self.projected_value_7d = self.intercept + self.slope * (len(self.values) + 168)


@dataclass
class StudentExperiment:
    """Top-level experiment definition.
    
    One student manages both ecosystems.
    """
    experiment_id: str
    student_name: str
    guild_id: int
    experiment_start: datetime
    
    # Strategy definitions
    strategy_a: MarketingStrategy
    strategy_b: MarketingStrategy
    
    # Hypotheses
    primary_hypothesis: str          # Why A will beat B
    alternative_hypothesis: str      # Why B might beat A
    success_criteria: List[str]       # What constitutes success
    
    # Experiment configuration
    test_duration_hours: int = 24
    sample_size_target: int = 500
    significance_level: float = 0.05  # α for statistical tests
    
    # Results (populated during experiment)
    comparison_results: List[ComparisonResult] = field(default_factory=list)
    final_value_scores: Dict[EcosystemLabel, ValueScore] = field(default_factory=dict)
    winner: Optional[EcosystemLabel] = None
    winner_confidence: float = 0.0
    
    # Manager notes
    notes: str = ""
    
    def get_best_performing_metric(self) -> Optional[str]:
        """Identify which metric shows clearest winner."""
        if not self.comparison_results:
            return None
        
        # Find result with highest probability of winner
        best = max(
            self.comparison_results,
            key=lambda r: max(r.probability_a_better, r.probability_b_better)
        )
        return best.test_metric
