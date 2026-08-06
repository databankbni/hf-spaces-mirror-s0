"""
Comparative GradeBot for mktbook_5

Scores student experiments based on:
- Slope of improvement (trajectory analysis)
- Effect size (practical significance)
- Strategy validity (did they fulfill the hypothesis?)
- Statistical rigor (sample size, confidence)
- Overall ecosystem health
"""

import logging
from typing import Dict, List, Optional, Tuple
from datetime import datetime

from models import (
    StudentExperiment, ValueScore, ComparisonResult,
    PerformanceTrajectory, EcosystemLabel, BayesianPosterior
)

logger = logging.getLogger(__name__)


class ComparativeGradeBot:
    """
    Grades student A/B experiments.
    
    Compares the "slope of improvement" between two strategies.
    Not just final score, but velocity of improvement.
    """
    
    def __init__(self, config, db):
        """
        Args:
            config: Configuration manager
            db: Database connection
        """
        self.config = config
        self.db = db
    
    async def grade_experiment(self, experiment: StudentExperiment,
                               trajectories: Dict[EcosystemLabel, PerformanceTrajectory],
                               comparisons: List[ComparisonResult],
                               value_scores: Dict[EcosystemLabel, ValueScore]) -> Dict:
        """
        Compare and grade an A/B experiment.
        
        Args:
            experiment: StudentExperiment object
            trajectories: Performance trajectories for each ecosystem
            comparisons: Bayesian comparison results
            value_scores: Final value scores for each ecosystem
        
        Returns:
            Comprehensive grade report
        """
        
        # Grade component 1: Trajectory Analysis (30%)
        trajectory_grade = self._grade_trajectories(trajectories)
        
        # Grade component 2: Statistical Rigor (25%)
        rigor_grade = self._grade_statistical_rigor(comparisons)
        
        # Grade component 3: Strategy Execution (25%)
        strategy_grade = self._grade_strategy_execution(experiment, value_scores)
        
        # Grade component 4: Clear Winner Emerged (20%)
        winner_grade = self._grade_winner_emergence(comparisons, value_scores)
        
        # Calculate weighted total
        final_grade = (
            (trajectory_grade * 0.30) +
            (rigor_grade * 0.25) +
            (strategy_grade * 0.25) +
            (winner_grade * 0.20)
        )
        
        # Determine which ecosystem won
        if experiment.comparison_results:
            best_comparison = max(
                experiment.comparison_results,
                key=lambda c: max(c.probability_a_better, c.probability_b_better)
            )
            winner_ecosystem = (
                EcosystemLabel.ECOSYSTEM_A
                if best_comparison.probability_a_better > best_comparison.probability_b_better
                else EcosystemLabel.ECOSYSTEM_B
            )
            winner_confidence = max(
                best_comparison.probability_a_better,
                best_comparison.probability_b_better
            )
        else:
            winner_ecosystem = None
            winner_confidence = 0.0
        
        # Compile grade report
        report = {
            "experiment_id": experiment.experiment_id,
            "student": experiment.student_name,
            "duration_hours": (datetime.now() - experiment.experiment_start).total_seconds() / 3600,
            
            # Component grades
            "trajectory_grade": trajectory_grade,      # Slope analysis
            "rigor_grade": rigor_grade,                # Statistical quality
            "strategy_grade": strategy_grade,          # Execution quality
            "winner_grade": winner_grade,              # Clarity of winner
            
            # Final grade
            "final_grade": final_grade,
            "final_grade_letter": self._score_to_letter(final_grade),
            
            # Winner analysis
            "winner_ecosystem": winner_ecosystem.value if winner_ecosystem else "Tie",
            "winner_confidence": winner_confidence,
            "winner_strategy": (
                experiment.strategy_a.name if winner_ecosystem == EcosystemLabel.ECOSYSTEM_A
                else experiment.strategy_b.name if winner_ecosystem == EcosystemLabel.ECOSYSTEM_B
                else "No clear winner"
            ),
            
            # Value scores
            "value_scores": {
                "ecosystem_a": value_scores.get(EcosystemLabel.ECOSYSTEM_A).total_value_score if EcosystemLabel.ECOSYSTEM_A in value_scores else 0,
                "ecosystem_b": value_scores.get(EcosystemLabel.ECOSYSTEM_B).total_value_score if EcosystemLabel.ECOSYSTEM_B in value_scores else 0
            },
            
            # Trajectory analysis
            "trajectories": {
                "ecosystem_a": {
                    "slope": trajectories[EcosystemLabel.ECOSYSTEM_A].slope if EcosystemLabel.ECOSYSTEM_A in trajectories else 0,
                    "r_squared": trajectories[EcosystemLabel.ECOSYSTEM_A].r_squared if EcosystemLabel.ECOSYSTEM_A in trajectories else 0,
                    "improvement_velocity": "Fast" if trajectories.get(EcosystemLabel.ECOSYSTEM_A, None) and trajectories[EcosystemLabel.ECOSYSTEM_A].slope > 2 else "Moderate" if trajectories.get(EcosystemLabel.ECOSYSTEM_A, None) and trajectories[EcosystemLabel.ECOSYSTEM_A].slope > 0.5 else "Slow"
                } if EcosystemLabel.ECOSYSTEM_A in trajectories else {},
                "ecosystem_b": {
                    "slope": trajectories[EcosystemLabel.ECOSYSTEM_B].slope if EcosystemLabel.ECOSYSTEM_B in trajectories else 0,
                    "r_squared": trajectories[EcosystemLabel.ECOSYSTEM_B].r_squared if EcosystemLabel.ECOSYSTEM_B in trajectories else 0,
                    "improvement_velocity": "Fast" if trajectories.get(EcosystemLabel.ECOSYSTEM_B, None) and trajectories[EcosystemLabel.ECOSYSTEM_B].slope > 2 else "Moderate" if trajectories.get(EcosystemLabel.ECOSYSTEM_B, None) and trajectories[EcosystemLabel.ECOSYSTEM_B].slope > 0.5 else "Slow"
                } if EcosystemLabel.ECOSYSTEM_B in trajectories else {}
            },
            
            # Feedback
            "feedback": self._generate_feedback(
                experiment, trajectory_grade, rigor_grade,
                strategy_grade, winner_grade, final_grade
            ),
            
            # Timestamp
            "graded_at": datetime.now().isoformat()
        }
        
        # Save to database
        await self._save_grade_to_db(report)
        
        return report
    
    def _grade_trajectories(self, trajectories: Dict[EcosystemLabel, PerformanceTrajectory]) -> float:
        """
        Grade the improvement velocities (slopes).
        
        Factors:
        - Did at least one ecosystem show clear improvement?
        - How fast did they improve?
        - Was improvement consistent (high R²)?
        - Did one improve measurably faster than the other?
        """
        
        if not trajectories or len(trajectories) < 2:
            return 0.0
        
        trajectory_a = trajectories.get(EcosystemLabel.ECOSYSTEM_A)
        trajectory_b = trajectories.get(EcosystemLabel.ECOSYSTEM_B)
        
        if not trajectory_a or not trajectory_b:
            return 0.0
        
        score = 50.0  # Base
        
        # Reward positive slopes
        slope_a = trajectory_a.slope
        slope_b = trajectory_b.slope
        
        if slope_a > 0:
            score += min(25, (slope_a / 5.0) * 25)  # 5 = max slope bonus
        if slope_b > 0:
            score += min(25, (slope_b / 5.0) * 25)
        
        # Reward consistency (high R² = stable trend)
        r2_a = trajectory_a.r_squared
        r2_b = trajectory_b.r_squared
        
        if r2_a > 0.7:
            score += 12.5
        if r2_b > 0.7:
            score += 12.5
        
        # Reward differential improvement
        slope_diff = abs(slope_a - slope_b)
        if slope_diff > 1.0:
            score += 10
        
        return min(100.0, max(0.0, score))
    
    def _grade_statistical_rigor(self, comparisons: List[ComparisonResult]) -> float:
        """
        Grade statistical quality of experiment.
        
        Factors:
        - Was significance level achieved? (p < 0.05)
        - High confidence in winner? (prob > 90%)
        - Appropriate sample size?
        - Clear effect size?
        """
        
        if not comparisons:
            return 0.0
        
        score = 50.0  # Base
        
        for comparison in comparisons:
            # Significance
            if comparison.p_value < 0.05:
                score += 15
            elif comparison.p_value < 0.10:
                score += 7.5
            
            # Confidence
            max_prob = max(comparison.probability_a_better, comparison.probability_b_better)
            if max_prob > 0.95:
                score += 15
            elif max_prob > 0.80:
                score += 10
            elif max_prob > 0.65:
                score += 5
            
            # Effect size (Cohen's d)
            effect = abs(comparison.effect_size)
            if effect > 0.8:  # Large
                score += 10
            elif effect > 0.5:  # Medium
                score += 5
            elif effect > 0.2:  # Small
                score += 2
        
        return min(100.0, max(0.0, score))
    
    def _grade_strategy_execution(self, experiment: StudentExperiment,
                                 value_scores: Dict[EcosystemLabel, ValueScore]) -> float:
        """
        Grade how well strategies were executed.
        
        Factors:
        - Did both strategies function? (No crashes/failures)
        - Did they achieve min thresholds?
        - Were success criteria met?
        - Quality of strategy definitions
        """
        
        score = 50.0  # Base
        
        # Check both ecosystems have value scores
        if EcosystemLabel.ECOSYSTEM_A in value_scores:
            score_a = value_scores[EcosystemLabel.ECOSYSTEM_A].total_value_score
            if score_a > 70:
                score += 15
            elif score_a > 50:
                score += 10
            elif score_a > 30:
                score += 5
        
        if EcosystemLabel.ECOSYSTEM_B in value_scores:
            score_b = value_scores[EcosystemLabel.ECOSYSTEM_B].total_value_score
            if score_b > 70:
                score += 15
            elif score_b > 50:
                score += 10
            elif score_b > 30:
                score += 5
        
        # Success criteria (hypothetical - would be checked against actual)
        success_count = len(experiment.success_criteria)
        if success_count >= 2:
            score += 10
        
        # Strategy clarity
        if len(experiment.primary_hypothesis) > 50:
            score += 10
        
        return min(100.0, max(0.0, score))
    
    def _grade_winner_emergence(self, comparisons: List[ComparisonResult],
                               value_scores: Dict[EcosystemLabel, ValueScore]) -> float:
        """
        Grade clarity and magnitude of winner.
        
        Factors:
        - Is there a clear winner? (95%+ probability)
        - How large is the difference?
        - Is winner consistent across metrics?
        """
        
        if not comparisons:
            return 0.0
        
        score = 50.0  # Base
        
        # Check for clear winner across comparisons
        clear_winners = 0
        for comparison in comparisons:
            max_prob = max(comparison.probability_a_better, comparison.probability_b_better)
            if max_prob > 0.95:
                clear_winners += 1
                score += 15
            elif max_prob > 0.80:
                score += 10
            elif max_prob < 0.67:
                score -= 5  # Indecisive result
        
        # Bonus for overwhelming victory
        if clear_winners == len(comparisons) and len(comparisons) >= 2:
            score += 15
        
        # Value score difference
        if EcosystemLabel.ECOSYSTEM_A in value_scores and EcosystemLabel.ECOSYSTEM_B in value_scores:
            score_a = value_scores[EcosystemLabel.ECOSYSTEM_A].total_value_score
            score_b = value_scores[EcosystemLabel.ECOSYSTEM_B].total_value_score
            diff = abs(score_a - score_b)
            
            if diff > 30:
                score += 15
            elif diff > 15:
                score += 10
            elif diff > 5:
                score += 5
        
        return min(100.0, max(0.0, score))
    
    def _score_to_letter(self, score: float) -> str:
        """Convert 0-100 score to letter grade."""
        if score >= 93:
            return "A"
        elif score >= 90:
            return "A-"
        elif score >= 87:
            return "B+"
        elif score >= 83:
            return "B"
        elif score >= 80:
            return "B-"
        elif score >= 77:
            return "C+"
        elif score >= 73:
            return "C"
        elif score >= 70:
            return "C-"
        elif score >= 60:
            return "D"
        else:
            return "F"
    
    def _generate_feedback(self, experiment: StudentExperiment,
                         trajectory_grade: float, rigor_grade: float,
                         strategy_grade: float, winner_grade: float,
                         final_grade: float) -> str:
        """Generate detailed feedback for student."""
        
        feedback = f"""
**Experiment Analysis for {experiment.student_name}**

**Primary Hypothesis:** {experiment.primary_hypothesis}
**Result:** {"SUPPORTED" if final_grade > 75 else "PARTIALLY SUPPORTED" if final_grade > 60 else "NOT SUPPORTED"}

**Component Breakdown:**
• Trajectory Analysis: {trajectory_grade:.0f}/100
  - How fast did strategies improve?
  - Consistency and velocity matter more than final score
  
• Statistical Rigor: {rigor_grade:.0f}/100
  - Did you collect enough data?
  - Statistical significance achieved?
  
• Strategy Execution: {strategy_grade:.0f}/100
  - Did both strategies function well?
  - Quality of experimental design?
  
• Winner Clarity: {winner_grade:.0f}/100
  - Is there a clear winner?
  - How dominant is the winning strategy?

**Overall Grade: {final_grade:.1f}/100 ({self._score_to_letter(final_grade)})**

**Recommendations:**
"""
        
        if trajectory_grade < 70:
            feedback += "- Your improvement slopes were inconsistent. Next time, focus on strategy clarity.\n"
        
        if rigor_grade < 70:
            feedback += "- Consider larger sample sizes or longer test windows for statistical power.\n"
        
        if strategy_grade < 70:
            feedback += "- One or both strategies underperformed. Review hypothesis alignment.\n"
        
        if winner_grade < 70:
            feedback += "- Results were too close to call definitively. Run longer or tweak strategy differentiation.\n"
        
        feedback += f"\n**Next Steps:** {self._get_next_steps(final_grade)}"
        
        return feedback
    
    def _get_next_steps(self, score: float) -> str:
        """Recommend next steps based on grade."""
        if score >= 90:
            return "Scale the winning strategy. Your data strongly supports it. Ready for production?"
        elif score >= 80:
            return "Good work! Continue testing with this winner or refine the loser strategy and rerun."
        elif score >= 70:
            return "Results suggest direction. Run a follow-up test with refined strategy definitions."
        elif score >= 60:
            return "Inconclusive. Collect more data or redesign your strategy hypotheses for clarity."
        else:
            return "Neither strategy performed well. Rethink your value proposition or target audience."
    
    async def _save_grade_to_db(self, report: Dict):
        """Save grade report to database."""
        
        try:
            await self.db.execute(
                """
                INSERT INTO experiment_grades (
                    experiment_id, student_name, final_grade,
                    trajectory_grade, rigor_grade, strategy_grade, winner_grade,
                    winner_ecosystem, winner_confidence, feedback, graded_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (report["experiment_id"], report["student"], report["final_grade"],
                 report["trajectory_grade"], report["rigor_grade"],
                 report["strategy_grade"], report["winner_grade"],
                 report["winner_ecosystem"], report["winner_confidence"],
                 report["feedback"], report["graded_at"])
            )
            await self.db.commit()
            logger.info(f"Saved grade report: {report['experiment_id']}")
        except Exception as e:
            logger.error(f"Error saving grade to database: {e}")
