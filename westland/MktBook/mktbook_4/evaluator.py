"""
Fashion Image Evaluator for mktbook_4

Analyzes generated fashion images using vision models.
Tracks aesthetic dimensions and trend adoption.
Provides detailed visual critiques for bot negotiation.
"""

import logging
from typing import Optional, Dict, Tuple
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


@dataclass
class VisualCritique:
    """Bot's verbal evaluation of a fashion image."""
    evaluator_name: str
    aesthetic_assessment: str  # Qualitative visual analysis
    aesthetic_scores: Dict[str, float]  # Scored aesthetic dimensions
    trend_relevance: str  # How this relates to current trends
    influence_score: float  # 0-100: did this impress me?
    adoption_likelihood: float  # 0-100: will I advocate for this trend?
    improvement_suggestions: str  # What could be better


class EvaluationStyle(Enum):
    """Different bot personalities for evaluation."""
    CRITICAL_EXPERT = "critical_expert"  # Harsh, fashion-forward
    PRAGMATIST = "pragmatist"  # Market appeal focused
    TREND_EVANGELIST = "trend_evangelist"  # Innovation-focused
    CULTURAL_ANALYST = "cultural_analyst"  # Diversity/representation focused


class ImageEvaluator:
    """Evaluate fashion images using vision AI and trend analysis."""
    
    def __init__(self, openai_client, config):
        """
        Args:
            openai_client: OpenAI async client (GPT-4V)
            config: Configuration manager
        """
        self.client = openai_client
        self.config = config
        self.vision_model = "gpt-4-vision-preview"
    
    async def evaluate_fashion_image(self, image_url: str, bot_name: str,
                                    bot_style: EvaluationStyle = EvaluationStyle.CRITICAL_EXPERT,
                                    fashion_context: str = "") -> VisualCritique:
        """
        Have a bot visually evaluate a fashion image.
        
        Args:
            image_url: URL of generated image
            bot_name: Name of evaluating bot
            bot_style: Personality style for evaluation
            fashion_context: Context about the fashion trend
        
        Returns:
            VisualCritique object with detailed assessment
        """
        
        prompt = self._build_evaluation_prompt(bot_name, bot_style, fashion_context)
        
        try:
            logger.info(f"Evaluating image as {bot_name} ({bot_style.value})...")
            
            response = await self.client.chat.completions.create(
                model=self.vision_model,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image_url",
                                "image_url": {"url": image_url}
                            },
                            {
                                "type": "text",
                                "text": prompt
                            }
                        ]
                    }
                ],
                max_tokens=800,
                temperature=0.8
            )
            
            critique_text = response.choices[0].message.content
            critique = self._parse_critique_response(critique_text, bot_name, bot_style)
            
            return critique
        
        except Exception as e:
            logger.error(f"Error evaluating image: {e}")
            return self._create_empty_critique(bot_name, bot_style)
    
    def _build_evaluation_prompt(self, bot_name: str, style: EvaluationStyle,
                                fashion_context: str) -> str:
        """Build a detailed prompt for image evaluation."""
        
        style_prompts = {
            EvaluationStyle.CRITICAL_EXPERT: (
                "You are a harsh, fashionable critic who demands innovation and precision. "
                "Focus on technical execution, trend-forward thinking, and originality. "
                "Be demanding but fair. Use specific fashion vocabulary."
            ),
            EvaluationStyle.PRAGMATIST: (
                "You are a practical fashion analyst focused on market appeal and wearability. "
                "Evaluate this from a consumer standpoint - would people actually wear this? "
                "Consider mass appeal, trend timing, and commercial viability."
            ),
            EvaluationStyle.TREND_EVANGELIST: (
                "You are excited about emerging trends and innovation. "
                "Look for what's fresh, bold, and ahead-of-curve. "
                "Highlight the trend leadership and cultural significance of this piece."
            ),
            EvaluationStyle.CULTURAL_ANALYST: (
                "You analyze fashion through cultural and social lenses. "
                "Consider diversity, representation, sustainability, and cultural relevance. "
                "Evaluate how this piece engages with contemporary cultural conversations."
            )
        }
        
        prompt = f"""You are {bot_name}, a fashion industry bot. {style_prompts[style]}

Analyze this fashion image across these dimensions:
1. COLOR_HARMONY (0-100): Do colors work together?
2. SILHOUETTE_CLARITY (0-100): Is the garment form distinctive?
3. TEXTURE_QUALITY (0-100): Does fabric/material quality show?
4. TREND_RELEVANCE (0-100): Is this current/forward-thinking?
5. ORIGINALITY (0-100): How unique/innovative?
6. BRAND_CONSISTENCY (0-100): Does it fit a coherent aesthetic vision?

Provide your response in this exact format:

ASSESSMENT: [2-3 sentence visual analysis of what you see]
SCORES: [COLOR_HARMONY: X, SILHOUETTE_CLARITY: X, TEXTURE_QUALITY: X, TREND_RELEVANCE: X, ORIGINALITY: X, BRAND_CONSISTENCY: X]
TREND_ANALYSIS: [1-2 sentences on how this relates to current fashion trends]
INFLUENCE: [0-100 number] - How impressed/influenced are you by this?
ADOPTION: [0-100 number] - Would you advocate for this trend?
SUGGESTIONS: [1-2 sentences on how this could be improved]
"""
        
        if fashion_context:
            prompt += f"\nContext: {fashion_context}"
        
        return prompt
    
    def _parse_critique_response(self, response_text: str, bot_name: str,
                                style: EvaluationStyle) -> VisualCritique:
        """Parse GPT response into VisualCritique dataclass."""
        
        try:
            # Extract sections from response
            lines = response_text.split('\n')
            assessment = self._extract_field(lines, "ASSESSMENT:", "")
            scores_str = self._extract_field(lines, "SCORES:", "")
            trend_analysis = self._extract_field(lines, "TREND_ANALYSIS:", "")
            influence = float(self._extract_field(lines, "INFLUENCE:", "50"))
            adoption = float(self._extract_field(lines, "ADOPTION:", "50"))
            suggestions = self._extract_field(lines, "SUGGESTIONS:", "")
            
            # Parse aesthetic scores
            aesthetic_scores = self._parse_scores(scores_str)
            
            return VisualCritique(
                evaluator_name=bot_name,
                aesthetic_assessment=assessment,
                aesthetic_scores=aesthetic_scores,
                trend_relevance=trend_analysis,
                influence_score=min(100, max(0, influence)),
                adoption_likelihood=min(100, max(0, adoption)),
                improvement_suggestions=suggestions
            )
        
        except Exception as e:
            logger.error(f"Error parsing critique: {e}")
            return self._create_empty_critique(bot_name, style)
    
    def _extract_field(self, lines: list, field_name: str, default: str) -> str:
        """Extract field value from response lines."""
        for line in lines:
            if field_name in line:
                return line.split(field_name, 1)[1].strip()
        return default
    
    def _parse_scores(self, scores_str: str) -> Dict[str, float]:
        """Parse comma-separated scores."""
        scores = {}
        try:
            for item in scores_str.split(','):
                if ':' in item:
                    key, val = item.split(':')
                    scores[key.strip()] = float(val.strip())
        except:
            pass
        return scores
    
    def _create_empty_critique(self, bot_name: str, style: EvaluationStyle) -> VisualCritique:
        """Create empty critique on error."""
        return VisualCritique(
            evaluator_name=bot_name,
            aesthetic_assessment="Unable to evaluate image",
            aesthetic_scores={},
            trend_relevance="",
            influence_score=0,
            adoption_likelihood=0,
            improvement_suggestions=""
        )
    
    async def aggregate_evaluations(self, critiques: list) -> Dict:
        """
        Aggregate multiple bot evaluations into trend metrics.
        
        Args:
            critiques: List of VisualCritique objects
        
        Returns:
            Dictionary with aggregated metrics
        """
        
        if not critiques:
            return {}
        
        # Average influence and adoption scores
        avg_influence = sum(c.influence_score for c in critiques) / len(critiques)
        avg_adoption = sum(c.adoption_likelihood for c in critiques) / len(critiques)
        
        # Consensus aesthetic scores
        all_scores = {}
        for critique in critiques:
            for dimension, score in critique.aesthetic_scores.items():
                if dimension not in all_scores:
                    all_scores[dimension] = []
                all_scores[dimension].append(score)
        
        consensus_aesthetic = {
            dim: sum(scores) / len(scores)
            for dim, scores in all_scores.items()
        }
        
        # Collect trend analyses
        trend_analyses = [c.trend_relevance for c in critiques if c.trend_relevance]
        
        return {
            "average_influence": avg_influence,
            "average_adoption": avg_adoption,
            "consensus_aesthetic": consensus_aesthetic,
            "trend_consensus": " | ".join(trend_analyses),
            "evaluation_count": len(critiques),
            "evaluators": [c.evaluator_name for c in critiques]
        }
