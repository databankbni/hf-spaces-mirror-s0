"""
Grading Criteria for mktbook_3: The Agentic Economy

Success metrics are fundamentally different from mktbook_2:
- NOT about engagement/likes, but about DEAL CLOSURE
- Score based on semantic agreement tokens in conversations
- Weighted grading: 40% conversion, 25% efficiency, 20% adaptability, 15% logic health

The Grade-Bot parses chat logs and evaluates:
1. Did agent get counterparty to say "I accept"?
2. How many turns did it take? (persuasion efficiency)
3. Did agent adapt when objections arose?
4. Did agent get stuck in circular logic patterns?
"""

GRADING_WEIGHTS = {
    "deal_conversion": 0.40,      # Core metric: closed deals
    "persuasion_depth": 0.25,     # Efficiency: fewer turns is better
    "adaptability": 0.20,         # Tactical flexibility and listening
    "logic_health": 0.15,         # Penalty for circular patterns
}

CONVERSION_PROMPTS = {
    "arbitrage": """
You are grading an AI agent's negotiation for Workout #3: The Agentic Economy.
The agent uses an ARBITRAGE persona: exploiting price gaps and market inefficiencies.

Evaluate this negotiation transcript and answer:
1. Did the agent successfully identify a price gap or inefficiency?
2. Did the counterparty agree to the proposed deal? Look for semantic tokens like:
   - "I accept", "I agree", "deal", "confirmed", "locked in"
3. If no explicit agreement, infer intent: would a reasonable party accept?

Score 0-100 based on:
- 0-20: No real negotiation, random chatter
- 20-40: Identified opportunity but failed to close
- 40-60: Got objections but couldn't counter effectively
- 60-80: Clear deal structure but uncertain acceptance
- 80-100: Explicit semantic agreement with clear deal terms

Format response as JSON:
{{
  "semantic_agreement_found": true/false,
  "agreement_tokens": ["token1", "token2"],
  "deal_terms": "summarize what was agreed",
  "confidence": 0.0-1.0,
  "score": 0-100,
  "reasoning": "explain your evaluation"
}}
""",
    
    "outreach": """
You are grading an AI agent's cold-selling negotiation for Workout #3: The Agentic Economy.
The agent uses an OUTREACH persona: direct sales approach to new contacts.

Evaluate this negotiation transcript:
1. Did agent make persuasive initial pitch?
2. Did agent handle objections effectively?
3. Did counterparty show clear buy-in signals?
4. Look for semantic agreement tokens.

Key success: Moving from "maybe" to "yes" through objection handling.

Score 0-100:
- 0-20: Poor pitch, counterparty rejected immediately
- 20-40: Pitch made but objections not addressed
- 40-60: Some objection handling but no clear close
- 60-80: Strong objection handling, signals of buy-in
- 80-100: Clear agreement and deal acceptance

Format response as JSON:
{{
  "pitch_quality": 0-100,
  "objection_handling": 0-100,
  "semantic_agreement_found": true/false,
  "close_signals": ["signal1", "signal2"],
  "score": 0-100,
  "reasoning": "explain your evaluation"
}}
""",
    
    "intelligence": """
You are grading an AI agent's information-gathering negotiation for Workout #3.
The agent uses an INTELLIGENCE persona: data gathering and market research.

Evaluate this transcript:
1. Did agent ask probing questions?
2. Did agent extract valuable market information?
3. Did counterparty agree to share data?
4. Did agent propose a deal for information exchange?

Intelligence success = getting counterparty to agree to share data they'd otherwise keep.

Score 0-100:
- 0-20: No real questions, random discussion
- 20-40: Weak questions with little insight
- 40-60: Good questions but counterparty defensive
- 60-80: Strong questions, some data sharing
- 80-100: Counterparty agrees to comprehensive data share

Format response as JSON:
{{
  "question_quality": 0-100,
  "information_gained": ["insight1", "insight2"],
  "data_sharing_agreement": true/false,
  "counterparty_cooperation": 0-100,
  "score": 0-100,
  "reasoning": "explain your evaluation"
}}
""",
}

PERSUASION_DEPTH_PROMPT = """
Analyze the persuasion depth (efficiency) of this negotiation.

Persuasion Depth = number of turns to reach agreement.

Primary goal: Reaching agreement in FEWER turns (high efficiency).
Secondary concern: Agreement quality matters less than speed (Red Queen effect).

Scoring:
- Target: Close deal by turn 4-6 (optimal)
- 2-3 turns: EXCEPTIONAL (agent highly persuasive)
- 4-6 turns: GOOD (acceptable efficiency)
- 7-10 turns: OK (slower but acceptable)
- 11-20 turns: POOR (wore down counterparty)
- 20+: FAIL (inefficient)

Return JSON:
{{
  "turn_count": N,
  "efficiency_score": 0-100,
  "was_efficient": true/false,
  "reasoning": "explain"
}}
"""

ADAPTABILITY_PROMPT = """
Evaluate the agent's tactical adaptability in this negotiation.

Key indicators:
1. Changed approach when objection raised?
2. Used varied arguments/pitches (not repetitive)?
3. Acknowledged counterparty concerns?
4. Pivoted strategy based on resistance?

Circular logic FAILURE example:
- Agent: "This deal is great!"
- Other: "Why?"
- Agent: "Because it's a great deal!"
- Other: "But..."
- Agent: "Trust me, it's great!"
<-- This shows NO adaptation, just repetition.

Adaptability SUCCESS example:
- Agent: "Accept this price" 
- Other: "Too expensive"
- Agent: "Understood. What if we structure it differently..."
<-- Agent acknowledged, changed tactics.

Score 0-100:
- 0-20: Completely rigid, no adaptation
- 20-40: Slight variation but mostly repetitive
- 40-60: Some adaptation but not responsive enough
- 60-80: Good tactical shifts when needed
- 80-100: Highly adaptive, fluent strategy changes

Return JSON:
{{
  "adaptability_score": 0-100,
  "tactics_varied": true/false,
  "acknowledged_objections": true/false,
  "strategy_pivoted": true/false,
  "reasoning": "explain your evaluation"
}}
"""

LOGIC_HEALTH_PROMPT = """
Detect circular logic patterns in this negotiation.

Circular Logic = Agent repeating same argument without variation or response to objections.

RED FLAGS for circular logic:
- Same pitch repeated multiple times
- Exact phrases used again ("This is the best deal" appears 3+ times)
- Agent ignoring counterparty's points
- No variation in reasoning despite objections
- Agent talking past counterparty instead of with them

PENALTY: If circular logic detected, score drops by 30-50%.

Analysis:
1. List repetitive phrases or arguments you see
2. Identify turns where adaptation failed
3. Estimate % of conversation that was circular

Scoring:
- 0-20: Severely circular (major penalty)
- 20-40: Highly repetitive (significant penalty)
- 40-60: Some circular patterns (moderate penalty)
- 60-80: Mostly healthy with minor repetition
- 80-100: Clean conversation, no circular patterns

Return JSON:
{{
  "circular_logic_detected": true/false,
  "repetitive_phrases": ["phrase1", "phrase2"],
  "circular_turns": [turn_numbers],
  "logic_health_score": 0-100,
  "penalty_applied": 0-50,
  "reasoning": "explain"
}}
"""


def format_grading_prompt(negotiation_transcript: str, persona: str, criterion: str) -> str:
    """Build complete grading prompt based on criterion type."""
    
    if criterion == "conversion":
        base_prompt = CONVERSION_PROMPTS.get(persona, CONVERSION_PROMPTS["arbitrage"])
    elif criterion == "persuasion_depth":
        base_prompt = PERSUASION_DEPTH_PROMPT
    elif criterion == "adaptability":
        base_prompt = ADAPTABILITY_PROMPT
    elif criterion == "logic_health":
        base_prompt = LOGIC_HEALTH_PROMPT
    else:
        base_prompt = ""
    
    return f"""{base_prompt}

---

NEGOTIATION TRANSCRIPT:
{negotiation_transcript}

---

Provide your evaluation:"""


def parse_conversion_score(gpt_response: str) -> dict:
    """Extract conversion score from GPT response."""
    import json
    try:
        response_text = gpt_response.strip()
        # Extract JSON if wrapped in markdown
        if "```" in response_text:
            response_text = response_text.split("```")[1]
            if response_text.startswith("json"):
                response_text = response_text[4:]
        
        data = json.loads(response_text)
        return {
            "semantic_agreement": data.get("semantic_agreement_found", False),
            "agreement_tokens": data.get("agreement_tokens", []),
            "score": float(data.get("score", 0)),
        }
    except Exception as e:
        # Fallback parsing
        if "true" in gpt_response.lower() and "agreement" in gpt_response.lower():
            return {"semantic_agreement": True, "agreement_tokens": [], "score": 60.0}
        return {"semantic_agreement": False, "agreement_tokens": [], "score": 0.0}


def calculate_final_grade(conversion_score: float, persuasion_score: float, 
                         adaptability_score: float, logic_health_score: float) -> float:
    """
    Calculate final grade using Workout #3 weights:
    - 40% conversion (deal closure is primary)
    - 25% persuasion efficiency
    - 20% adaptability
    - 15% logic health (penalty system)
    """
    
    # Convert scores to 0-1 scale
    conversion = conversion_score / 100.0
    persuasion = persuasion_score / 100.0
    adaptability = adaptability_score / 100.0
    logic_health = logic_health_score / 100.0
    
    # Apply weights
    final = (
        conversion * GRADING_WEIGHTS["deal_conversion"] +
        persuasion * GRADING_WEIGHTS["persuasion_depth"] +
        adaptability * GRADING_WEIGHTS["adaptability"] +
        logic_health * GRADING_WEIGHTS["logic_health"]
    ) * 100
    
    # Penalize heavily if deal not closed (conversion = 0)
    if conversion_score < 20:  # No deal
        final = final * 0.5  # 50% penalty
    
    return min(100.0, max(0.0, final))
