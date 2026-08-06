"""
Bayesian A/B Testing Engine for mktbook_5

Implements Westland's Bayesian Framework for comparative decision-making.
Tracks priors, posteriors, and generates credible intervals.
Students don't need math expertise - engine handles statistics.
"""

import logging
import math
from typing import Dict, Tuple, Optional, List
from datetime import datetime
import numpy as np
from scipy import stats as scipy_stats

from models import (
    EcosystemLabel, BayesianObservation, BayesianPosterior, ComparisonResult
)

logger = logging.getLogger(__name__)


class BayesianABEngine:
    """
    Westland's Bayesian A/B Decision Framework
    
    Implements:
    - Prior specification (initial beliefs)
    - Likelihood (probability of observations given hypotheses)
    - Posterior distribution (updated beliefs after data)
    - Credible intervals (Bayesian confidence regions)
    """
    
    def __init__(self, prior_mean: float = 50.0, prior_variance: float = 100.0):
        """
        Initialize with default priors.
        
        Args:
            prior_mean: Prior belief about metric value (default: neutral at 50)
            prior_variance: Prior uncertainty (100 = wide/uncertain)
        """
        self.prior_mean = prior_mean
        self.prior_variance = prior_variance
        
        # Store observations for both ecosystems
        self.observations_a: List[BayesianObservation] = []
        self.observations_b: List[BayesianObservation] = []
        
        # Posterior estimates
        self.posterior_a: Optional[BayesianPosterior] = None
        self.posterior_b: Optional[BayesianPosterior] = None
        
        # Comparison results
        self.last_comparison: Optional[ComparisonResult] = None
    
    def add_observation(self, ecosystem: EcosystemLabel, bot_name: str,
                       metric_type: str, observed_value: float,
                       variance: float = 1.0):
        """
        Add a single observation to the Bayesian model.
        
        Args:
            ecosystem: ECOSYSTEM_A or ECOSYSTEM_B
            bot_name: Name of bot generating data
            metric_type: "engagement", "conversion", "revenue", etc.
            observed_value: The measurement
            variance: Confidence/uncertainty in this measurement
        """
        
        obs = BayesianObservation(
            observation_id=f"{ecosystem.value}_{datetime.now().isoformat()}",
            ecosystem=ecosystem,
            bot_name=bot_name,
            timestamp=datetime.now(),
            metric_type=metric_type,
            observed_value=observed_value,
            variance=variance
        )
        
        if ecosystem == EcosystemLabel.ECOSYSTEM_A:
            self.observations_a.append(obs)
        else:
            self.observations_b.append(obs)
        
        logger.info(f"Added observation for {ecosystem.value}: {metric_type}={observed_value:.2f}")
    
    def update_posterior(self, ecosystem: EcosystemLabel, bot_name: str,
                        metric_type: str) -> BayesianPosterior:
        """
        Update posterior distribution using conjugate prior/likelihood.
        
        Uses Normal-Normal conjugacy:
        - Prior: N(μ₀, σ₀²)
        - Likelihood: N(x, σ²)
        - Posterior: N(μ₁, σ₁²) [updated mean and variance]
        
        Args:
            ecosystem: ECOSYSTEM_A or ECOSYSTEM_B
            bot_name: Bot name
            metric_type: Metric type
        
        Returns:
            BayesianPosterior with updated distribution
        """
        
        # Get observations for this ecosystem
        if ecosystem == EcosystemLabel.ECOSYSTEM_A:
            observations = self.observations_a
        else:
            observations = self.observations_b
        
        # Filter for this metric type
        relevant_obs = [o for o in observations if o.metric_type == metric_type]
        
        if not relevant_obs:
            logger.warning(f"No observations for {ecosystem.value}/{metric_type}")
            return self._create_null_posterior(ecosystem, bot_name, metric_type)
        
        # Normal-Normal conjugate update
        # Prior parameters
        mu0 = self.prior_mean
        sigma0_sq = self.prior_variance
        
        # Likelihood parameters (from observations)
        observed_values = [o.observed_value for o in relevant_obs]
        observed_variances = [o.variance for o in relevant_obs]
        
        # Average of observations
        x_bar = np.mean(observed_values)
        n = len(observed_values)
        
        # Average variance (measurement uncertainty)
        sigma_sq = np.mean(observed_variances)
        
        # Posterior parameters (Bayesian update)
        precision_prior = 1.0 / sigma0_sq if sigma0_sq > 0 else 0
        precision_likelihood = n / sigma_sq if sigma_sq > 0 else 0
        
        precision_posterior = precision_prior + precision_likelihood
        
        if precision_posterior > 0:
            mu1 = (precision_prior * mu0 + precision_likelihood * x_bar) / precision_posterior
            sigma1_sq = 1.0 / precision_posterior
        else:
            mu1 = x_bar
            sigma1_sq = sigma_sq
        
        # Credible interval (95%)
        z_critical = 1.96  # 95% confidence
        ci_lower = mu1 - z_critical * np.sqrt(sigma1_sq)
        ci_upper = mu1 + z_critical * np.sqrt(sigma1_sq)
        
        posterior = BayesianPosterior(
            ecosystem=ecosystem,
            bot_name=bot_name,
            metric_type=metric_type,
            posterior_mean=float(mu1),
            posterior_variance=float(sigma1_sq),
            posterior_std=float(np.sqrt(sigma1_sq)),
            credible_interval_lower=float(ci_lower),
            credible_interval_upper=float(ci_upper),
            prior_mean=mu0,
            prior_variance=sigma0_sq,
            observation_count=n,
            update_timestamp=datetime.now()
        )
        
        if ecosystem == EcosystemLabel.ECOSYSTEM_A:
            self.posterior_a = posterior
        else:
            self.posterior_b = posterior
        
        logger.info(
            f"Updated posterior for {ecosystem.value}: "
            f"μ={mu1:.2f} ±{np.sqrt(sigma1_sq):.2f}, CI=[{ci_lower:.2f}, {ci_upper:.2f}]"
        )
        
        return posterior
    
    def compare_ecosystems(self, metric_type: str) -> ComparisonResult:
        """
        Compare two ecosystems using Bayesian hypothesis testing.
        
        Calculates:
        - P(A > B | data): Probability A is better
        - P(B > A | data): Probability B is better
        - P(A ≈ B | data): Probability they're equivalent
        - Effect size (Cohen's d)
        - Practical recommendation
        
        Args:
            metric_type: Which metric to compare
        
        Returns:
            ComparisonResult object
        """
        
        if not self.posterior_a or not self.posterior_b:
            logger.warning("Posteriors not initialized for comparison")
            return self._create_null_comparison()
        
        # Extract posterior parameters
        mu_a = self.posterior_a.posterior_mean
        sigma_a = self.posterior_a.posterior_std
        
        mu_b = self.posterior_b.posterior_mean
        sigma_b = self.posterior_b.posterior_std
        
        # Difference distribution: D = A - B
        # D ~ N(μ_a - μ_b, σ_a² + σ_b²)
        mu_diff = mu_a - mu_b
        sigma_diff = np.sqrt(sigma_a**2 + sigma_b**2)
        
        # Effect size (Cohen's d)
        pooled_std = np.sqrt((sigma_a**2 + sigma_b**2) / 2)
        effect_size = mu_diff / pooled_std if pooled_std > 0 else 0
        
        # Calculate probabilities using standard normal
        # P(A > B) = P(D > 0)
        z_score_zero = -mu_diff / sigma_diff if sigma_diff > 0 else 0
        prob_a_better = 1.0 - scipy_stats.norm.cdf(z_score_zero)
        prob_b_better = scipy_stats.norm.cdf(z_score_zero)
        
        # P(A ≈ B): probability difference is within equivalence margin
        equivalence_margin = 5.0  # Practical significance threshold
        z_eq_lower = (-equivalence_margin - mu_diff) / sigma_diff if sigma_diff > 0 else -np.inf
        z_eq_upper = (equivalence_margin - mu_diff) / sigma_diff if sigma_diff > 0 else np.inf
        prob_equivalent = scipy_stats.norm.cdf(z_eq_upper) - scipy_stats.norm.cdf(z_eq_lower)
        
        # Classical t-test for comparison
        t_stat = mu_diff / sigma_diff if sigma_diff > 0 else 0
        df = self.posterior_a.observation_count + self.posterior_b.observation_count - 2
        p_value = 2 * (1.0 - scipy_stats.t.cdf(abs(t_stat), df)) if df > 0 else 1.0
        
        # Determine recommendation
        if prob_a_better > 0.95:
            recommendation = f"Scale Ecosystem A: {prob_a_better*100:.0f}% confident it outperforms B"
            winner = EcosystemLabel.ECOSYSTEM_A
        elif prob_b_better > 0.95:
            recommendation = f"Scale Ecosystem B: {prob_b_better*100:.0f}% confident it outperforms A"
            winner = EcosystemLabel.ECOSYSTEM_B
        elif prob_equivalent > 0.80:
            recommendation = "Equivalent performance - continue testing or choose based on other factors"
            winner = None
        else:
            recommendation = "Continue testing - results still inconclusive"
            winner = None
        
        # Credible interval for difference
        ci_diff_lower = mu_diff - 1.96 * sigma_diff
        ci_diff_upper = mu_diff + 1.96 * sigma_diff
        
        result = ComparisonResult(
            comparison_id=f"compare_{datetime.now().isoformat()}",
            test_metric=metric_type,
            ecosystem_a=EcosystemLabel.ECOSYSTEM_A,
            ecosystem_b=EcosystemLabel.ECOSYSTEM_B,
            mean_diff=float(mu_diff),
            effect_size=float(effect_size),
            t_statistic=float(t_stat),
            p_value=float(p_value),
            credible_interval=(float(ci_diff_lower), float(ci_diff_upper)),
            probability_a_better=float(prob_a_better),
            probability_b_better=float(prob_b_better),
            probability_equivalent=float(prob_equivalent),
            recommendation=recommendation,
            confidence_level=float(max(prob_a_better, prob_b_better)),
            comparison_timestamp=datetime.now()
        )
        
        self.last_comparison = result
        
        logger.info(
            f"Comparison result for {metric_type}:\n"
            f"  A > B: {prob_a_better*100:.1f}%\n"
            f"  B > A: {prob_b_better*100:.1f}%\n"
            f"  Equivalent: {prob_equivalent*100:.1f}%\n"
            f"  Effect size: {effect_size:.2f}\n"
            f"  p-value: {p_value:.4f}"
        )
        
        return result
    
    def get_trajectory_prediction(self, ecosystem: EcosystemLabel,
                                 metric_type: str, hours_ahead: int = 24) -> float:
        """
        Predict future performance based on trajectory and posterior.
        
        Uses drift rate from observed improvements.
        
        Args:
            ecosystem: Which ecosystem
            metric_type: Which metric
            hours_ahead: Hours to project forward
        
        Returns:
            Predicted value
        """
        
        posterior = self.posterior_a if ecosystem == EcosystemLabel.ECOSYSTEM_A else self.posterior_b
        
        if not posterior or posterior.observation_count < 2:
            return posterior.posterior_mean if posterior else 50.0
        
        # Estimate drift rate from posterior improvement
        # Simplified: assume drift towards higher value based on effect size
        drift_rate = 0.5  # 0.5 points per hour (configurable)
        
        predicted = posterior.posterior_mean + (drift_rate * hours_ahead)
        
        return min(100.0, max(0.0, predicted))
    
    def _create_null_posterior(self, ecosystem: EcosystemLabel,
                             bot_name: str, metric_type: str) -> BayesianPosterior:
        """Create empty posterior on error."""
        return BayesianPosterior(
            ecosystem=ecosystem,
            bot_name=bot_name,
            metric_type=metric_type,
            posterior_mean=self.prior_mean,
            posterior_variance=self.prior_variance,
            posterior_std=math.sqrt(self.prior_variance),
            credible_interval_lower=self.prior_mean - 1.96 * math.sqrt(self.prior_variance),
            credible_interval_upper=self.prior_mean + 1.96 * math.sqrt(self.prior_variance),
            prior_mean=self.prior_mean,
            prior_variance=self.prior_variance,
            observation_count=0,
            update_timestamp=datetime.now()
        )
    
    def _create_null_comparison(self) -> ComparisonResult:
        """Create null comparison on error."""
        return ComparisonResult(
            comparison_id="null",
            test_metric="unknown",
            ecosystem_a=EcosystemLabel.ECOSYSTEM_A,
            ecosystem_b=EcosystemLabel.ECOSYSTEM_B,
            mean_diff=0.0,
            effect_size=0.0,
            t_statistic=0.0,
            p_value=1.0,
            credible_interval=(0.0, 0.0),
            probability_a_better=0.5,
            probability_b_better=0.5,
            probability_equivalent=1.0,
            recommendation="Insufficient data",
            confidence_level=0.0,
            comparison_timestamp=datetime.now()
        )
    
    def get_summary_stats(self) -> Dict:
        """Get human-readable summary of current Bayesian state."""
        
        return {
            "prior": {
                "mean": self.prior_mean,
                "variance": self.prior_variance
            },
            "ecosystem_a": {
                "observations": len(self.observations_a),
                "posterior": {
                    "mean": self.posterior_a.posterior_mean if self.posterior_a else None,
                    "std": self.posterior_a.posterior_std if self.posterior_a else None,
                    "credible_interval": (
                        self.posterior_a.credible_interval_lower,
                        self.posterior_a.credible_interval_upper
                    ) if self.posterior_a else None
                } if self.posterior_a else {}
            },
            "ecosystem_b": {
                "observations": len(self.observations_b),
                "posterior": {
                    "mean": self.posterior_b.posterior_mean if self.posterior_b else None,
                    "std": self.posterior_b.posterior_std if self.posterior_b else None,
                    "credible_interval": (
                        self.posterior_b.credible_interval_lower,
                        self.posterior_b.credible_interval_upper
                    ) if self.posterior_b else None
                } if self.posterior_b else {}
            },
            "last_comparison": {
                "prob_a_better": self.last_comparison.probability_a_better if self.last_comparison else None,
                "prob_b_better": self.last_comparison.probability_b_better if self.last_comparison else None,
                "recommendation": self.last_comparison.recommendation if self.last_comparison else None
            } if self.last_comparison else {}
        }
