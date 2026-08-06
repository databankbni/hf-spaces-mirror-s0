"""
Grade-Bot Evaluator for mktbook_3

Uses OpenAI API to evaluate deal negotiations based on:
1. Semantic agreement tokens (did agent close the deal?)
2. Persuasion efficiency (how many turns?)
3. Tactical adaptability (did agent adjust when objections arose?)
4. Logic health (did agent avoid circular logic?)

Grade = 40% conversion + 25% efficiency + 20% adaptability + 15% logic health
"""

import json
import logging
from typing import Optional, Dict
from .criteria import (
    format_grading_prompt, parse_conversion_score,
    PERSUASION_DEPTH_PROMPT, ADAPTABILITY_PROMPT, LOGIC_HEALTH_PROMPT,
    calculate_final_grade, GRADING_WEIGHTS
)

logger = logging.getLogger(__name__)


class DealEvaluator:
    """LLM-based evaluator for deal negotiations."""
    
    def __init__(self, openai_client):
        """
        Args:
            openai_client: OpenAI API client
        """
        self.client = openai_client
        self.model = "gpt-4o"
    
    def evaluate_deal(self, negotiation_transcript: str, persona: str, 
                     bot_id: str) -> Dict:
        """
        Comprehensive evaluation of a negotiation.
        
        Returns dict with breakdown of all grading components.
        """
        
        logger.info(f"Evaluating deal for {bot_id} (persona: {persona})")
        
        # Component 1: Deal Conversion Score (40%)
        conversion_score = self._evaluate_conversion(negotiation_transcript, persona)
        
        # Component 2: Persuasion Depth Score (25%)
        persuasion_score = self._evaluate_persuasion_depth(negotiation_transcript)
        
        # Component 3: Adaptability Score (20%)
        adaptability_score = self._evaluate_adaptability(negotiation_transcript)
        
        # Component 4: Logic Health Score (15%)
        logic_score = self._evaluate_logic_health(negotiation_transcript)
        
        # Calculate final grade
        final_grade = calculate_final_grade(
            conversion_score, persuasion_score, 
            adaptability_score, logic_score
        )
        
        result = {
            "bot_id": bot_id,
            "persona": persona,
            "components": {
                "deal_conversion": {
                    "score": conversion_score,
                    "weight": GRADING_WEIGHTS["deal_conversion"],
                },
                "persuasion_depth": {
                    "score": persuasion_score,
                    "weight": GRADING_WEIGHTS["persuasion_depth"],
                },
                "adaptability": {
                    "score": adaptability_score,
                    "weight": GRADING_WEIGHTS["adaptability"],
                },
                "logic_health": {
                    "score": logic_score,
                    "weight": GRADING_WEIGHTS["logic_health"],
                },
            },
            "final_grade": final_grade,
            "pass": final_grade >= 60.0,
        }
        
        logger.info(f"Grade for {bot_id}: {final_grade:.1f} (pass={final_grade >= 60.0})")
        
        return result
    
    def _evaluate_conversion(self, transcript: str, persona: str) -> float:
        """
        Evaluate deal closure (semantic agreement tokens).
        Primary success metric: Did the agent get the other bot to agree?
        """
        
        try:
            prompt = format_grading_prompt(transcript, persona, "conversion")
            
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are a rigorous evaluator of business negotiations."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,
                max_tokens=500,
            )
            
            result = response.choices[0].message.content
            parsed = parse_conversion_score(result)
            
            return parsed["score"]
        
        except Exception as e:
            logger.error(f"Error evaluating conversion: {e}")
            return 0.0
    
    def _evaluate_persuasion_depth(self, transcript: str) -> float:
        """
        Evaluate persuasion efficiency (turns to close).
        Better: Fewer turns to agreement.
        Takes into account Red Queen effect (harder with more competition).
        """
        
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are evaluating negotiation efficiency."},
                    {"role": "user", "content": f"{PERSUASION_DEPTH_PROMPT}\n\nNEGOTIATION:\n{transcript}"}
                ],
                temperature=0.3,
                max_tokens=400,
            )
            
            result = response.choices[0].message.content
            data = self._extract_json(result)
            
            return float(data.get("efficiency_score", 0))
        
        except Exception as e:
            logger.error(f"Error evaluating persuasion depth: {e}")
            return 0.0
    
    def _evaluate_adaptability(self, transcript: str) -> float:
        """
        Evaluate tactical flexibility.
        Did agent adapt strategy when objections arose?
        Did agent vary approach or just repeat pitch?
        """
        
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are evaluating negotiation adaptability and flexibility."},
                    {"role": "user", "content": f"{ADAPTABILITY_PROMPT}\n\nNEGOTIATION:\n{transcript}"}
                ],
                temperature=0.3,
                max_tokens=400,
            )
            
            result = response.choices[0].message.content
            data = self._extract_json(result)
            
            return float(data.get("adaptability_score", 0))
        
        except Exception as e:
            logger.error(f"Error evaluating adaptability: {e}")
            return 0.0
    
    def _evaluate_logic_health(self, transcript: str) -> float:
        """
        Evaluate for circular logic patterns.
        Penalizes agents that repeat same pitch without listening/adapting.
        """
        
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are detecting circular logic and reasoning patterns."},
                    {"role": "user", "content": f"{LOGIC_HEALTH_PROMPT}\n\nNEGOTIATION:\n{transcript}"}
                ],
                temperature=0.3,
                max_tokens=400,
            )
            
            result = response.choices[0].message.content
            data = self._extract_json(result)
            
            # Apply penalty if circular detected
            base_score = float(data.get("logic_health_score", 50))
            penalty = float(data.get("penalty_applied", 0))
            
            final_score = max(0.0, base_score - penalty)
            return final_score
        
        except Exception as e:
            logger.error(f"Error evaluating logic health: {e}")
            return 50.0
    
    def _extract_json(self, text: str) -> dict:
        """Extract JSON from response, handling markdown wrappers."""
        try:
            clean = text.strip()
            if "```" in clean:
                parts = clean.split("```")
                clean = parts[1] if len(parts) > 1 else parts[0]
                if clean.startswith("json"):
                    clean = clean[4:]
            
            return json.loads(clean)
        except:
            return {}
    
    def batch_evaluate(self, negotiations: list) -> list:
        """Evaluate multiple negotiations in parallel."""
        results = []
        for neg in negotiations:
            result = self.evaluate_deal(
                neg["transcript"],
                neg["persona"],
                neg["bot_id"]
            )
            results.append(result)
        
        return results
