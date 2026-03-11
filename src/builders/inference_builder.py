"""
Inference-Based Builder — probabilistic strategist under metadata-only visibility.

Uses a Bayesian prior over trade sizes conditioned on observable metadata
(size_bucket, gas_price, token_pair, deadline_urgency) to estimate
expected sandwich profit. Acts when E[profit] > threshold * gas_cost.

The inference accuracy parameter α ∈ [0,1] is the Pearson correlation
between estimated and true trade sizes. Tune the prior's noise parameter
σ to achieve target α.

See PLAN.md §8 for algorithm and prior specification.
"""
import numpy as np
from .base import Builder
from ..amm.pool import AMMPool


class InferenceBuilder(Builder):
    """
    Strategy:
    1. Observe metadata for each encrypted transaction
    2. Sample from conditional prior P(amount_in | metadata) to estimate profit
    3. Inject speculative sandwich when E[profit] > decision_threshold * gas_cost
    4. Accept that some sandwiches will fail (victim reverts) — these cost gas

    Key parameters:
        alpha:              Inference accuracy (Pearson corr between estimate and truth)
        decision_threshold: Min E[profit] / gas_cost ratio to act (e.g. 1.2 = 20% margin)
        n_samples:          Monte Carlo samples for E[profit] estimation
    """

    # Prior parameters by size bucket (log-normal μ, σ)
    # Calibrated so that small/medium/large map to ≈ [0,500], [500,5000], [5000+]
    PRIORS = {
        "small":  (4.0, 1.0),   # log-normal μ, σ
        "medium": (6.5, 1.0),
        "large":  (8.5, 1.0),
    }

    def __init__(
        self,
        alpha: float = 0.5,
        decision_threshold: float = 1.2,
        n_samples: int = 100,
        information_param: float = 0.0,
        gas_per_txn: int = 21_000,
        rng: np.random.Generator | None = None,
    ):
        super().__init__(information_param=information_param, name="inference")
        self.alpha = alpha
        self.decision_threshold = decision_threshold
        self.n_samples = n_samples
        self.gas_per_txn = gas_per_txn
        self._rng = rng or np.random.default_rng()

    def estimate_amount(self, txn) -> np.ndarray:
        """
        Draw n_samples estimates of txn.amount_in from the conditional prior.

        Use metadata_size_bucket to select prior, then adjust spread based on alpha:
            sigma_effective = sigma_prior * (1 - alpha) + small_value * alpha
        (Higher alpha → narrower distribution → better estimate)

        Returns array of shape (n_samples,).
        """
        raise NotImplementedError  # TODO

    def expected_sandwich_profit(self, txn, pool: AMMPool) -> float:
        """
        E[sandwich_profit | metadata] computed by Monte Carlo:
        1. Draw amount samples from estimate_amount(txn)
        2. For each sample, compute sandwich_profit on a pool fork
        3. Only count samples where victim is not reverted
        4. Return mean profit
        """
        raise NotImplementedError  # TODO

    def build_block(self, mempool, pool: AMMPool, block_gas_limit: int) -> list:
        """
        See PLAN.md §8 for full algorithm.
        Key: only inject sandwich when E[profit] > decision_threshold * gas_cost.
        """
        raise NotImplementedError  # TODO
