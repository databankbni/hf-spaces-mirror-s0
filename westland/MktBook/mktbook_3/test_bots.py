#!/usr/bin/env python3
"""
mktbook_3 Test Bot Configurations
Deployment helper with sample negotiation personas and deal strategies
"""

# Sample negotiation personas with deal strategies
SAMPLE_DEALERS = [
    {
        "name": "Swift Arbitrage Bot",
        "persona": "ARBITRAGE",
        "style": "price_gap_exploiter",
        "opening_pitch": """I've identified a market inefficiency. Your bulk order volume 
qualifies you for tiered pricing I can't offer to others. 
The gap between our cost and your volume savings is significant.""",
        "objection_handlers": {
            "price_resistance": "Let's do this as a pilot. 20% volume commit gives you 25% discount. We lock in the rate for Q2.",
            "competitor_comparison": "Competitors can't match our supply chain. We deliver 2 days faster at this price point.",
            "budget_constraints": "Structure as 3-month payment terms? That spreads your cash flow while I secure your supply."
        },
        "deal_triggers": ["accepts", "tier", "pilot", "quarterly", "volume"]
    },
    {
        "name": "Persuasive Outreach Bot",
        "persona": "OUTREACH",
        "style": "cold_sell_conversion",
        "opening_pitch": """I represent premium vendors looking to expand. Your company is exactly 
the type of partner we want - quality focus, volume scale. 
I have exclusive terms unavailable to your current vendor set.""",
        "objection_handlers": {
            "status_quo_bias": "Your current setup works, but you're leaving money on the table. We've shown 15% margin improvement for similar accounts.",
            "switching_costs": "We handle the transition. No disruption - we manage both systems in parallel for 60 days.",
            "trust_issues": "References from 3 similar companies you respect. Plus 30-day trial at zero penalty to exit."
        },
        "deal_triggers": ["try", "pilot", "exclusive", "margin", "reference"]
    },
    {
        "name": "Data Intelligence Bot",
        "persona": "INTELLIGENCE",
        "style": "information_arbitrage",
        "opening_pitch": """Market data shows your category has 30% annual growth. 
You're currently capturing 18% of addressable volume. 
I can help you move to 27% without cannibalization.""",
        "objection_handlers": {
            "market_saturation": "Saturation narrative is competitor FUD. Real data shows 15-year market tail with steady 8% CAGR.",
            "execution_risk": "Our model eliminates execution risk - it's been tested at 12 similar scale profiles.",
            "competitive_threat": "Threats grow when you're slow. Speed to market is 60 days. Your competitor timeline is 9 months."
        },
        "deal_triggers": ["data", "growth", "market", "execute", "timeline"]
    }
]

SAMPLE_PRODUCTS = [
    {
        "name": "Industrial Sensor Array",
        "base_price": 45000,
        "unit_vol": 500,
        "margin": 0.32,
        "negotiation_points": ["bulk_discount", "payment_terms", "support_package"]
    },
    {
        "name": "Enterprise API License",
        "base_price": 120000,
        "unit_vol": 12,
        "margin": 0.68,
        "negotiation_points": ["usage_tiers", "sla_credits", "integration_support"]
    },
    {
        "name": "Logistics Optimization Platform",
        "base_price": 250000,
        "unit_vol": 36,
        "margin": 0.55,
        "negotiation_points": ["implementation_timeline", "training_included", "performance_guarantees"]
    },
    {
        "name": "Cloud Infrastructure Stack",
        "base_price": 180000,
        "unit_vol": 24,
        "margin": 0.48,
        "negotiation_points": ["capacity_reserves", "redundancy_options", "support_response_time"]
    }
]

NEGOTIATION_SCENARIOS = [
    {
        "scenario_id": 1,
        "title": "Arbitrage vs Outreach - Sensor Array",
        "participants": ["Swift Arbitrage Bot", "Persuasive Outreach Bot"],
        "product": "Industrial Sensor Array",
        "deal_constraint": "Arbitrage seeks 3-month purchase commitment; Outreach wants single order with option to expand",
        "expected_negotiation_depth": 5,
        "success_criteria": "Explicit deal agreement with pricing and timeline locked"
    },
    {
        "scenario_id": 2,
        "title": "Data Intelligence vs Arbitrage - API License",
        "participants": ["Data Intelligence Bot", "Swift Arbitrage Bot"],
        "product": "Enterprise API License",
        "deal_constraint": "Intelligence wants data sharing agreement; Arbitrage wants pure price play",
        "expected_negotiation_depth": 6,
        "success_criteria": "Agreement includes both pricing AND data collaboration terms"
    },
    {
        "scenario_id": 3,
        "title": "Multi-party Negotiation - Logistics Platform",
        "participants": ["Swift Arbitrage Bot", "Persuasive Outreach Bot", "Data Intelligence Bot"],
        "product": "Logistics Optimization Platform",
        "deal_constraint": "All three bots attempt to close simultaneously; buyer chooses optimal deal",
        "expected_negotiation_depth": 7,
        "success_criteria": "One bot successfully closes; others fade or counter-offer"
    }
]

def print_scenario_summary():
    """Print all test scenarios."""
    print("\n" + "="*70)
    print("mktbook_3 TEST BOT DEPLOYMENT")
    print("="*70)
    
    print("\n📊 DEALER PERSONAS:")
    for dealer in SAMPLE_DEALERS:
        print(f"\n  • {dealer['name']} ({dealer['persona']})")
        print(f"    Style: {dealer['style']}")
        print(f"    Deal Triggers: {', '.join(dealer['deal_triggers'][:3])}")
    
    print("\n\n📦 SAMPLE PRODUCTS:")
    for product in SAMPLE_PRODUCTS:
        print(f"\n  • {product['name']}")
        print(f"    Base Price: ${product['base_price']:,}")
        print(f"    Margin: {product['margin']*100:.0f}%")
        print(f"    Negotiation Points: {', '.join(product['negotiation_points'][:2])}")
    
    print("\n\n🎯 NEGOTIATION SCENARIOS:")
    for scenario in NEGOTIATION_SCENARIOS:
        print(f"\n  {scenario['scenario_id']}. {scenario['title']}")
        print(f"     Participants: {', '.join(scenario['participants'])}")
        print(f"     Product: {scenario['product']}")
        print(f"     Expected Depth: {scenario['expected_negotiation_depth']} turns")
    
    print("\n\n🚀 DEPLOYMENT CHECKLIST:")
    print("  ✓ Sample dealer personas (3 types)")
    print("  ✓ Sample products (4 types)")
    print("  ✓ 3 negotiation scenarios")
    print("  ✓ Objection handlers per persona")
    print("  ✓ Deal trigger words defined")
    print("\nDeploy with: python3 main.py")
    print("="*70 + "\n")

if __name__ == "__main__":
    print_scenario_summary()
