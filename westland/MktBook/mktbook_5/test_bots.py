"""
Test Bot Configurations for mktbook_5

This file demonstrates how students can define their own marketing strategies
and deploy them. Customize these for your A/B testing experiments.
"""

from models import (
    StrategyType, MarketingStrategy, ProductListing,
    EcosystemLabel, StudentExperiment
)


# ============================================================================
# SAMPLE PRODUCT LISTINGS (for testing)
# ============================================================================

SAMPLE_PRODUCTS = [
    ProductListing(
        product_id="prod_tech_watch",
        name="SmartPro Watch",
        description="Advanced fitness tracking and notification management",
        price=299.99,
        category="Wearables",
        brand="TechFlow",
        unique_selling_points=[
            "10-day battery life",
            "Military-grade waterproofing",
            "AI-powered health coaching",
            "Works with all major platforms"
        ],
        discount_available=True,
        discount_percent=20
    ),
    ProductListing(
        product_id="prod_home_light",
        name="Ambient Home Lighting System",
        description="Smart RGB lighting that adapts to your circadian rhythm",
        price=189.99,
        category="Smart Home",
        brand="LuminaHome",
        unique_selling_points=[
            "Sunrise/sunset simulation",
            "Voice control integration",
            "Energy-efficient LED",
            "Reduces eye strain"
        ],
        discount_available=True,
        discount_percent=15
    ),
    ProductListing(
        product_id="prod_coffee_maker",
        name="PrecisionBrew Coffee Maker",
        description="Temperature-controlled brewing for perfect coffee every time",
        price=249.99,
        category="Kitchen",
        brand="CafeMaster",
        unique_selling_points=[
            "Precise temperature control",
            "Built-in grinder",
            "Mobile app scheduling",
            "Sustainable materials"
        ],
        discount_available=False,
        discount_percent=None
    ),
    ProductListing(
        product_id="prod_headphones",
        name="NoiseShield Pro Headphones",
        description="Professional-grade noise cancellation with 40-hour battery",
        price=399.99,
        category="Audio",
        brand="SoundLab",
        unique_selling_points=[
            "Adaptive noise cancellation",
            "40-hour battery life",
            "Premium build quality",
            "Certified sustainable"
        ],
        discount_available=True,
        discount_percent=25
    ),
    ProductListing(
        product_id="prod_desk_ergonomic",
        name="FlexiDesk Ergonomic Workstation",
        description="Height-adjustable desk with memory presets and health monitoring",
        price=499.99,
        category="Office Equipment",
        brand="WorkWell",
        unique_selling_points=[
            "Height 22-49 inches adjustable",
            "Posture monitoring via built-in sensor",
            "Quiet motor",
            "3-year warranty"
        ],
        discount_available=False,
        discount_percent=None
    )
]


# ============================================================================
# EXAMPLE STRATEGY A: AGGRESSIVE + VISUAL
# ============================================================================

STRATEGY_A_AGGRESSIVE_VISUAL = MarketingStrategy(
    name="Aggressive & Visual Marketing",
    primary_strategy=StrategyType.AGGRESSIVE,
    secondary_strategy=StrategyType.VISUAL,
    hypothesis="Hard-sell with eye-catching visuals and urgency will drive 50% higher conversion than passive approach",
    target_audience="Early adopters, deal-seekers, FOMO-motivated segments",
    value_proposition="Limited-time exclusive deal with premium features",
    engagement_prediction=75.0,
    conversion_prediction=12.0
)


# ============================================================================
# EXAMPLE STRATEGY B: PASSIVE + TEXTUAL
# ============================================================================

STRATEGY_B_PASSIVE_TEXTUAL = MarketingStrategy(
    name="Passive & Textual Marketing",
    primary_strategy=StrategyType.PASSIVE,
    secondary_strategy=StrategyType.TEXTUAL,
    hypothesis="Relationship-building through narrative will create more loyal customers with higher lifetime value than aggressive approach",
    target_audience="Thoughtful consumers, value-conscious segment, quality-focused",
    value_proposition="Aligned with your values and sustainable future",
    engagement_prediction=55.0,
    conversion_prediction=8.0
)


# ============================================================================
# EXAMPLE STRATEGY C: TECHNICAL + DATA-DRIVEN
# ============================================================================

STRATEGY_C_TECHNICAL_DATA = MarketingStrategy(
    name="Technical & Data-Driven Marketing",
    primary_strategy=StrategyType.TECHNICAL,
    secondary_strategy=StrategyType.TEXTUAL,
    hypothesis="Spec-focused transparent approach will resonate with technical buyers and build credibility",
    target_audience="Technical professionals, engineers, data-driven decision-makers",
    value_proposition="Proven specifications with competitive benchmarking",
    engagement_prediction=65.0,
    conversion_prediction=9.0
)


# ============================================================================
# EXAMPLE STRATEGY D: EMOTIONAL + LIFESTYLE
# ============================================================================

STRATEGY_D_EMOTIONAL_LIFESTYLE = MarketingStrategy(
    name="Emotional & Lifestyle Marketing",
    primary_strategy=StrategyType.EMOTIONAL,
    secondary_strategy=StrategyType.VISUAL,
    hypothesis="Aspirational identity alignment will create brand advocates who evangelize to networks",
    target_audience="Lifestyle-conscious, influencer-receptive, community-driven",
    value_proposition="A statement about who you are and your values",
    engagement_prediction=70.0,
    conversion_prediction=10.0
)


# ============================================================================
# SAMPLE EXPERIMENTS
# ============================================================================

def create_sample_experiment_aggressive_vs_passive(student_name: str, guild_id: int):
    """
    Create a sample Aggressive vs. Passive experiment.
    
    Hypothesis: Hard-sell strategies convert faster but passive builds loyalty
    Test Metric: Engagement speed vs. sentiment retention
    """
    
    from datetime import datetime
    
    return StudentExperiment(
        experiment_id=f"exp_aggr_passive_{datetime.now().timestamp()}",
        student_name=student_name,
        guild_id=guild_id,
        experiment_start=datetime.now(),
        strategy_a=STRATEGY_A_AGGRESSIVE_VISUAL,
        strategy_b=STRATEGY_B_PASSIVE_TEXTUAL,
        primary_hypothesis=(
            "Aggressive visual marketing with urgency and social proof will achieve "
            "2x faster conversion rate than passive textual approach"
        ),
        alternative_hypothesis=(
            "Passive approach will build stronger customer relationships and higher "
            "lifetime value despite slower initial conversion"
        ),
        success_criteria=[
            "5%+ engagement rate in leading strategy",
            "2%+ conversion rate in leading strategy",
            "Statistically significant difference (p < 0.05)",
            "Clear momentum/trajectory in winning strategy"
        ]
    )


def create_sample_experiment_technical_vs_emotional(student_name: str, guild_id: int):
    """
    Create a sample Technical vs. Emotional experiment.
    
    Hypothesis: Different buyer personas respond to different angles
    Test Metric: Engagement by audience segment quality
    """
    
    from datetime import datetime
    
    return StudentExperiment(
        experiment_id=f"exp_tech_emotion_{datetime.now().timestamp()}",
        student_name=student_name,
        guild_id=guild_id,
        experiment_start=datetime.now(),
        strategy_a=STRATEGY_C_TECHNICAL_DATA,
        strategy_b=STRATEGY_D_EMOTIONAL_LIFESTYLE,
        primary_hypothesis=(
            "Technical/data-driven marketing will attract higher-quality buyers "
            "with lower price sensitivity"
        ),
        alternative_hypothesis=(
            "Emotional/lifestyle marketing will drive higher engagement and advocacy "
            "despite lower initial willingness to pay"
        ),
        success_criteria=[
            "Differentiated engagement patterns by segment",
            "Revenue per customer comparison",
            "Sentiment trajectory over time",
            "Word-of-mouth/influence factor"
        ]
    )
