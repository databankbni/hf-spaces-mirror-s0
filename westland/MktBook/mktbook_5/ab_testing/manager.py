"""
A/B Testing Framework for mktbook_5

Manages experiment lifecycle:
- Experiment setup and candidate strategy definition
- Real-time metric collection
- Engagement tracking
- Conversion tracking
- Revenue tracking
"""

import logging
from typing import List, Optional, Dict
from datetime import datetime, timedelta
import uuid

from models import (
    EcosystemLabel, MarketingStrategy, EngagementMetrics,
    BotInteraction, PerformanceTrajectory, ValueScore,
    StudentExperiment
)

logger = logging.getLogger(__name__)


class ABTestManager:
    """Manages A/B test lifecycle and metric collection."""
    
    def __init__(self, config, db):
        """
        Args:
            config: Configuration manager
            db: Database connection
        """
        self.config = config
        self.db = db
        
        # Active experiments
        self.experiments: Dict[str, StudentExperiment] = {}
        
        # Metrics collection
        self.metrics_log: List[EngagementMetrics] = []
        self.interaction_log: List[BotInteraction] = []
        
        # Performance trajectories
        self.trajectories: Dict[str, Dict[EcosystemLabel, PerformanceTrajectory]] = {}
    
    async def create_experiment(self, student_name: str, guild_id: int,
                               strategy_a: MarketingStrategy,
                               strategy_b: MarketingStrategy,
                               primary_hypothesis: str,
                               alternative_hypothesis: str,
                               success_criteria: List[str]) -> StudentExperiment:
        """
        Create a new A/B experiment.
        
        Args:
            student_name: Student managing this test
            guild_id: Discord guild where run
            strategy_a: First marketing strategy
            strategy_b: Second marketing strategy
            primary_hypothesis: Why A will win
            alternative_hypothesis: Why B might win
            success_criteria: What constitutes success
        
        Returns:
            StudentExperiment object
        """
        
        experiment = StudentExperiment(
            experiment_id=str(uuid.uuid4()),
            student_name=student_name,
            guild_id=guild_id,
            experiment_start=datetime.now(),
            strategy_a=strategy_a,
            strategy_b=strategy_b,
            primary_hypothesis=primary_hypothesis,
            alternative_hypothesis=alternative_hypothesis,
            success_criteria=success_criteria
        )
        
        self.experiments[experiment.experiment_id] = experiment
        
        # Initialize trajectories
        self.trajectories[experiment.experiment_id] = {
            EcosystemLabel.ECOSYSTEM_A: PerformanceTrajectory(
                ecosystem=EcosystemLabel.ECOSYSTEM_A,
                bot_name=strategy_a.name,
                metric_type="engagement"
            ),
            EcosystemLabel.ECOSYSTEM_B: PerformanceTrajectory(
                ecosystem=EcosystemLabel.ECOSYSTEM_B,
                bot_name=strategy_b.name,
                metric_type="engagement"
            )
        }
        
        logger.info(f"Created experiment {experiment.experiment_id} for {student_name}")
        
        await self._save_experiment_to_db(experiment)
        
        return experiment
    
    async def log_interaction(self, experiment_id: str, interaction: BotInteraction):
        """
        Log a single bot-user interaction.
        
        Args:
            experiment_id: Which experiment
            interaction: BotInteraction object
        """
        
        self.interaction_log.append(interaction)
        
        # Save to database
        try:
            await self.db.execute(
                """
                INSERT INTO interactions (
                    experiment_id, interaction_id, bot_name, ecosystem,
                    timestamp, engagement_type, sentiment_score
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (experiment_id, interaction.interaction_id, interaction.bot_name,
                 interaction.ecosystem.value, interaction.timestamp,
                 interaction.engagement_type, interaction.sentiment_score)
            )
            await self.db.commit()
        except Exception as e:
            logger.error(f"Error logging interaction: {e}")
    
    async def update_metrics(self, experiment_id: str,
                            metrics: EngagementMetrics):
        """
        Update metrics for a bot/ecosystem in an experiment.
        
        Args:
            experiment_id: Which experiment
            metrics: EngagementMetrics object with updated counts
        """
        
        self.metrics_log.append(metrics)
        
        # Update trajectory
        if experiment_id in self.trajectories:
            trajectory = self.trajectories[experiment_id][metrics.ecosystem]
            engagement_score = metrics.calculate_engagement_score()
            trajectory.add_observation(metrics.metric_timestamp, engagement_score)
        
        # Save to database
        try:
            await self.db.execute(
                """
                INSERT INTO metrics (
                    experiment_id, bot_name, ecosystem, timestamp,
                    impressions, clicks, inquiries, conversions,
                    engagement_rate, conversion_rate, revenue_generated
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (experiment_id, metrics.bot_name, metrics.ecosystem.value,
                 metrics.metric_timestamp, metrics.impressions, metrics.clicks,
                 metrics.inquiries, metrics.conversions, metrics.engagement_rate,
                 metrics.conversion_rate, metrics.revenue_generated)
            )
            await self.db.commit()
        except Exception as e:
            logger.error(f"Error updating metrics: {e}")
    
    async def get_experiment_summary(self, experiment_id: str) -> Dict:
        """
        Get current status of an experiment.
        
        Args:
            experiment_id: Which experiment
        
        Returns:
            Dictionary with experiment status
        """
        
        if experiment_id not in self.experiments:
            return {}
        
        experiment = self.experiments[experiment_id]
        
        # Get trajectories
        trajectories = self.trajectories.get(experiment_id, {})
        
        summary = {
            "experiment_id": experiment_id,
            "student": experiment.student_name,
            "started": experiment.experiment_start.isoformat(),
            "strategy_a": {
                "name": experiment.strategy_a.name,
                "type": f"{experiment.strategy_a.primary_strategy.value}+{experiment.strategy_a.secondary_strategy.value if experiment.strategy_a.secondary_strategy else '?'}",
                "hypothesis": experiment.strategy_a.hypothesis
            },
            "strategy_b": {
                "name": experiment.strategy_b.name,
                "type": f"{experiment.strategy_b.primary_strategy.value}+{experiment.strategy_b.secondary_strategy.value if experiment.strategy_b.secondary_strategy else '?'}",
                "hypothesis": experiment.strategy_b.hypothesis
            },
            "trajectories": {
                "ecosystem_a": {
                    "slope": trajectories.get(EcosystemLabel.ECOSYSTEM_A, _null_trajectory()).slope,
                    "current_value": trajectories.get(EcosystemLabel.ECOSYSTEM_A, _null_trajectory()).values[-1] if trajectories.get(EcosystemLabel.ECOSYSTEM_A, _null_trajectory()).values else 0,
                    "projected_24h": trajectories.get(EcosystemLabel.ECOSYSTEM_A, _null_trajectory()).projected_value_24h
                } if EcosystemLabel.ECOSYSTEM_A in trajectories else {},
                "ecosystem_b": {
                    "slope": trajectories.get(EcosystemLabel.ECOSYSTEM_B, _null_trajectory()).slope,
                    "current_value": trajectories.get(EcosystemLabel.ECOSYSTEM_B, _null_trajectory()).values[-1] if trajectories.get(EcosystemLabel.ECOSYSTEM_B, _null_trajectory()).values else 0,
                    "projected_24h": trajectories.get(EcosystemLabel.ECOSYSTEM_B, _null_trajectory()).projected_value_24h
                } if EcosystemLabel.ECOSYSTEM_B in trajectories else {}
            }
        }
        
        return summary
    
    async def _save_experiment_to_db(self, experiment: StudentExperiment):
        """Save experiment definition to database."""
        
        try:
            await self.db.execute(
                """
                INSERT INTO experiments (
                    experiment_id, student_name, guild_id,
                    strategy_a, strategy_b,
                    hypothesis_a, notes,
                    test_duration_hours, significance_level
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (experiment.experiment_id, experiment.student_name,
                 experiment.guild_id, experiment.strategy_a.name,
                 experiment.strategy_b.name, experiment.primary_hypothesis,
                 experiment.notes, experiment.test_duration_hours,
                 experiment.significance_level)
            )
            await self.db.commit()
        except Exception as e:
            logger.error(f"Error saving experiment: {e}")


def _null_trajectory() -> PerformanceTrajectory:
    """Return empty trajectory for missing data."""
    return PerformanceTrajectory(
        ecosystem=EcosystemLabel.ECOSYSTEM_A,
        bot_name="",
        metric_type="",
        timestamps=[],
        values=[]
    )


class MetricsAggregator:
    """Aggregate metrics across multiple interactions/bots."""
    
    @staticmethod
    def aggregate_engagement(metrics_list: List[EngagementMetrics]) -> EngagementMetrics:
        """Combine multiple metric objects into aggregate."""
        
        if not metrics_list:
            return EngagementMetrics(
                session_id="empty",
                bot_name="aggregate",
                ecosystem=EcosystemLabel.ECOSYSTEM_A,
                metric_timestamp=datetime.now()
            )
        
        aggregate = EngagementMetrics(
            session_id=f"aggregate_{datetime.now().isoformat()}",
            bot_name="aggregate",
            ecosystem=metrics_list[0].ecosystem,
            metric_timestamp=datetime.now()
        )
        
        # Sum all values
        aggregate.impressions = sum(m.impressions for m in metrics_list)
        aggregate.clicks = sum(m.clicks for m in metrics_list)
        aggregate.inquiries = sum(m.inquiries for m in metrics_list)
        aggregate.conversions = sum(m.conversions for m in metrics_list)
        aggregate.revenue_generated = sum(m.revenue_generated for m in metrics_list)
        
        # Calculate rates
        if aggregate.impressions > 0:
            aggregate.engagement_rate = aggregate.clicks / aggregate.impressions
            aggregate.conversion_rate = aggregate.conversions / aggregate.impressions
        
        return aggregate
    
    @staticmethod
    def calculate_value_score(ecosystem_a_metrics: EngagementMetrics,
                             ecosystem_b_metrics: EngagementMetrics) -> tuple:
        """
        Calculate value scores for both ecosystems.
        
        Returns:
            (value_score_a, value_score_b)
        """
        
        def _calc_score(metrics: EngagementMetrics) -> ValueScore:
            score = ValueScore(
                ecosystem=metrics.ecosystem,
                bot_name=metrics.bot_name,
                score_timestamp=datetime.now(),
                engagement_component=metrics.calculate_engagement_score() * 0.8,  # CTR-based
                conversion_component=min(100, metrics.conversion_rate * 100),
                revenue_component=metrics.revenue_generated / 100.0 if metrics.revenue_generated else 0,  # Normalize
                influence_component=50.0  # Placeholder - would use social metrics
            )
            score.calculate_total()
            return score
        
        return _calc_score(ecosystem_a_metrics), _calc_score(ecosystem_b_metrics)
