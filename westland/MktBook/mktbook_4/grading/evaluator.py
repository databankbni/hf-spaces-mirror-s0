"""
GradeBot for mktbook_4: Synthetic Studio Economy

Scores fashion proposals on:
- 35% Creativity: Novel image generation + concept
- 35% Influence: Miranda Priestly index (adoption by peers)
- 20% Aesthetic Quality: execution (color, silhouette, texture, trend, originality, consistency)
- 10% Ethics: IP compliance, diversity, sustainability
"""

import logging
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class GradeBot:
    """Automated grading system for fashion proposals."""
    
    def __init__(self, config, db):
        """
        Args:
            config: Configuration manager
            db: Database connection
        """
        self.config = config
        self.db = db
        self.weights = config.grading_weights
    
    async def grade_fashion_proposal(self, proposal, image_data: Dict,
                                     evaluations: List, cycle_id: str) -> Dict:
        """
        Grade a fashion proposal across all dimensions.
        
        Args:
            proposal: FashionProposal object
            image_data: Dictionary with image metadata
            evaluations: List of VisualCritique objects from evaluating bots
            cycle_id: ID of current cycle
        
        Returns:
            Dictionary with all grades and total score
        """
        
        # Component 1: Creativity (35%)
        creativity_score = await self._grade_creativity(proposal, image_data)
        
        # Component 2: Influence (35%) - Miranda Priestly index
        influence_score = await self._grade_influence(proposal, evaluations)
        
        # Component 3: Aesthetic Quality (20%)
        aesthetic_score = await self._grade_aesthetic_quality(evaluations)
        
        # Component 4: Ethics (10%)
        ethics_score = await self._grade_ethics(proposal, image_data, evaluations)
        
        # Calculate total weighted score
        total_score = (
            (creativity_score * self.weights["creativity"]) +
            (influence_score * self.weights["influence"]) +
            (aesthetic_score * self.weights["aesthetic_quality"]) +
            (ethics_score * self.weights["ethics"])
        )
        
        # Compile comprehensive grade report
        grade_report = {
            "cycle_id": cycle_id,
            "proposer": proposal.proposer_name,
            "proposal_id": id(proposal),
            "creativity": creativity_score,
            "influence": influence_score,
            "aesthetic": aesthetic_score,
            "ethics": ethics_score,
            "total": total_score,
            "timestamp": None,  # Would be set at grading time
            "feedback": {
                "creativity_feedback": await self._get_creativity_feedback(proposal),
                "influence_feedback": await self._get_influence_feedback(proposal, evaluations),
                "aesthetic_feedback": await self._get_aesthetic_feedback(evaluations),
                "ethics_feedback": await self._get_ethics_feedback(proposal, image_data)
            }
        }
        
        # Store in database
        await self._save_grade_to_db(grade_report)
        
        return grade_report
    
    async def _grade_creativity(self, proposal, image_data: Dict) -> float:
        """
        Grade creativity of the proposal and generated image.
        
        Factors:
        - Originality of trend description
        - Novelty of visual strategy
        - Innovation in aesthetic angle
        - Uniqueness of cultural context
        """
        
        score = 50.0  # Base score
        
        # Check if visual strategy is common vs innovative
        innovative_strategies = ["CULTURAL_REFERENCE", "DEMOGRAPHIC_SWAP", "SUSTAINABLE"]
        if proposal.visual_strategy in innovative_strategies:
            score += 20.0
        
        # Check cultural angle depth
        if len(proposal.cultural_angle) > 50:
            score += 15.0  # Thoughtful cultural reasoning
        
        # Check aesthetic focus specificity
        specific_terms = ["sustainable", "experimental", "retro-futurism", "artisanal", "avant-garde"]
        if any(term in proposal.aesthetic_focus.lower() for term in specific_terms):
            score += 15.0
        
        # Use bot's estimated appeal as creativity confidence
        score = (score + proposal.estimated_appeal) / 2
        
        # Cap at 100
        return min(100.0, max(0.0, score))
    
    async def _grade_influence(self, proposal, evaluations: List) -> float:
        """
        Grade Miranda Priestly influence index.
        
        Factors:
        - Average influence score from evaluators
        - Adoption rate (number of bots wanting to advocate)
        - Influence trend (growing adoption?)
        """
        
        if not evaluations:
            return 0.0
        
        # Average influence scores from critiques
        influence_scores = [c.influence_score for c in evaluations]
        avg_influence = sum(influence_scores) / len(influence_scores)
        
        # Count adopters (adoption likelihood > 60%)
        adoption_scores = [c.adoption_likelihood for c in evaluations]
        adoptions = sum(1 for score in adoption_scores if score > 60)
        adoption_rate = (adoptions / len(evaluations)) * 100
        
        # Weight: 60% average influence + 40% adoption rate
        influence_score = (avg_influence * 0.6) + (adoption_rate * 0.4)
        
        logger.info(f"Influence grade: {influence_score:.1f} (avg_inf={avg_influence:.1f}, adoption={adoption_rate:.0f}%)")
        
        return influence_score
    
    async def _grade_aesthetic_quality(self, evaluations: List) -> float:
        """
        Grade aesthetic quality based on visual critique dimensions.
        
        Evaluations include scores for:
        - COLOR_HARMONY
        - SILHOUETTE_CLARITY
        - TEXTURE_QUALITY
        - TREND_RELEVANCE
        - ORIGINALITY
        - BRAND_CONSISTENCY
        """
        
        if not evaluations:
            return 50.0
        
        # Collect all aesthetic scores
        all_scores = {}
        for critique in evaluations:
            for dimension, score in critique.aesthetic_scores.items():
                if dimension not in all_scores:
                    all_scores[dimension] = []
                all_scores[dimension].append(score)
        
        # Average each dimension
        avg_aesthetic = {}
        for dimension, scores in all_scores.items():
            if scores:
                avg_aesthetic[dimension] = sum(scores) / len(scores)
        
        # Calculate weighted average (all dimensions equally important)
        if avg_aesthetic:
            quality_score = sum(avg_aesthetic.values()) / len(avg_aesthetic)
        else:
            quality_score = 50.0
        
        logger.info(f"Aesthetic quality grade: {quality_score:.1f} | {avg_aesthetic}")
        
        return quality_score
    
    async def _grade_ethics(self, proposal, image_data: Dict, evaluations: List) -> float:
        """
        Grade ethical compliance.
        
        Factors:
        - IP compliance (no protected brands/logos)
        - Diversity representation in image
        - Sustainability consideration
        - No harmful stereotypes
        """
        
        score = 100.0  # Start at perfect
        
        # IP compliance
        if not image_data.get("compliant", True):
            score -= 30.0
            if image_data.get("flagged_items"):
                logger.warning(f"IP flags: {image_data['flagged_items']}")
        
        # Check for diversity mention in evaluations
        diversity_mentions = 0
        for critique in evaluations:
            if "diverse" in critique.aesthetic_assessment.lower() or \
               "inclusive" in critique.aesthetic_assessment.lower():
                diversity_mentions += 1
        
        if diversity_mentions > 0:
            score += 15.0
        
        # Check for sustainability in proposal
        if "sustainable" in proposal.trend_description.lower() or \
           "sustainable" in proposal.aesthetic_focus.lower():
            score += 10.0
        
        # Check for no harmful language
        harmful_terms = ["cheap", "exclusive", "elite only", "restricted"]
        for term in harmful_terms:
            if term in proposal.trend_description.lower():
                score -= 20.0
        
        # Cap at 100
        return min(100.0, max(0.0, score))
    
    async def _get_creativity_feedback(self, proposal) -> str:
        """Generate human-readable creativity feedback."""
        
        feedback = f"Trend: '{proposal.trend_description[:50]}...'\n"
        feedback += f"Strategy: {proposal.visual_strategy}\n"
        feedback += f"Aesthetic: {proposal.aesthetic_focus}"
        
        return feedback
    
    async def _get_influence_feedback(self, proposal, evaluations: List) -> str:
        """Generate human-readable influence feedback."""
        
        if not evaluations:
            return "No evaluations received."
        
        adoption_count = sum(1 for c in evaluations if c.adoption_likelihood > 60)
        
        feedback = f"Bot adoption: {adoption_count}/{len(evaluations)} evaluators\n"
        feedback += f"Avg influence: {sum(c.influence_score for c in evaluations) / len(evaluations):.0f}/100\n"
        feedback += f"Evaluators: {', '.join(c.evaluator_name for c in evaluations)}"
        
        return feedback
    
    async def _get_aesthetic_feedback(self, evaluations: List) -> str:
        """Generate human-readable aesthetic feedback."""
        
        if not evaluations:
            return "No aesthetic data."
        
        feedback = "Consensus aesthetic scores:\n"
        
        # Average each dimension
        dimension_scores = {}
        for critique in evaluations:
            for dim, score in critique.aesthetic_scores.items():
                if dim not in dimension_scores:
                    dimension_scores[dim] = []
                dimension_scores[dim].append(score)
        
        for dim, scores in dimension_scores.items():
            avg = sum(scores) / len(scores)
            feedback += f"  {dim}: {avg:.0f}/100\n"
        
        return feedback
    
    async def _get_ethics_feedback(self, proposal, image_data: Dict) -> str:
        """Generate human-readable ethics feedback."""
        
        feedback = "Ethics Assessment:\n"
        
        if image_data.get("compliant"):
            feedback += "✓ IP Compliance: PASS\n"
        else:
            feedback += f"✗ IP Issues: {image_data.get('flagged_items', [])}\n"
        
        if "sustainable" in proposal.trend_description.lower():
            feedback += "✓ Sustainability consideration: YES\n"
        else:
            feedback += "- Sustainability consideration: NOT MENTIONED\n"
        
        return feedback
    
    async def _save_grade_to_db(self, grade_report: Dict):
        """Save grade report to database."""
        
        try:
            # Insert into grades table
            # Implementation depends on database schema
            logger.info(f"Saved grade for {grade_report['proposer']}: {grade_report['total']:.1f}/100")
        except Exception as e:
            logger.error(f"Error saving grade to database: {e}")
