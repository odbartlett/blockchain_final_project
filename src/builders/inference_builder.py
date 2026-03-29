"""
Inference-Based Builder — probabilistic strategist under metadata-only visibility.

Uses a Bayesian prior over trade sizes conditioned on observable metadata
(size_bucket, gas_price, token_pair, deadline_urgency) to estimate
expected sandwich profit. Acts when E[profit] > threshold * gas_cost.

The inference accuracy parameter α ∈ [0,1] controls the prior's spread:
  α = 0  →  prior at full sigma (noisy guesses, most sandwiches mis-sized)
  α = 1  →  prior collapsed to median (consistent guesses, near-optimal sizing)

See PLAN.md §8 for algorithm and prior specification.
"""
import numpy as np
from .base import Builder, make_builder_txn
from ..amm.pool import AMMPool

_GAS_PER_TXN = 21_000


class InferenceBuilder(Builder):
    """
    Strategy:
    1. Observe metadata for each transaction (works on both visible and encrypted)
    2. Sample from conditional prior P(amount_in | metadata) to estimate profit
    3. Inject speculative sandwich when E[profit] > decision_threshold * gas_cost
    4. Accept that some sandwiches will fail — these cost gas but don't contribute profit

    Key parameters:
        alpha:              Inference accuracy ∈ [0,1]. Controls prior spread.
        decision_threshold: Min E[profit] / gas_cost ratio to act (e.g. 1.2 = 20% margin)
        n_samples:          Monte Carlo samples for E[profit] estimation
    """

    # Log-normal prior per size bucket: (μ, σ)
    # Calibrated so each bucket's mass overlaps its [lower, upper] range
    PRIORS = {
        "small":  (4.0, 1.0),   # median ≈ 55,  covers [1, 500]
        "medium": (6.5, 1.0),   # median ≈ 665, covers [500, 5000]
        "large":  (8.5, 1.5),   # median ≈ 4915, covers [5000, ∞)
    }

    def __init__(
        self,
        alpha: float = 0.5,
        decision_threshold: float = 1.2,
        n_samples: int = 50,
        information_param: float = 0.0,
        gas_per_txn: float = 2.0,
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

        Prior is selected by size_bucket. Spread is controlled by alpha:
            sigma_eff = sigma_prior * (1 - alpha)
        Higher alpha → narrower distribution → estimates cluster near prior median.
        At alpha=1, sigma_eff ≈ 0 → all samples collapse to e^mu (the median).

        Returns integer array of shape (n_samples,).
        """
        mu, sigma_prior = self.PRIORS.get(txn.metadata_size_bucket, (6.5, 1.0))
        sigma_eff = max(sigma_prior * (1.0 - self.alpha), 1e-3)
        samples = self._rng.lognormal(mean=mu, sigma=sigma_eff, size=self.n_samples)
        return np.maximum(1, samples.astype(int))

    def expected_sandwich_profit(self, txn, pool: AMMPool) -> float:
        """
        E[sandwich_profit | metadata] computed by Monte Carlo over the prior.

        For each sampled amount:
        - Compute optimal front-run and simulate sandwich on a pool fork
        - Only count samples where victim is not reverted (valid sandwich)
        - Return mean profit across all samples (0 for invalid samples)

        The assumed min_amount_out for an encrypted tx uses default slippage (1%).
        """
        samples = self.estimate_amount(txn)
        profits = []
        for amount in samples:
            amount = int(amount)
            front = pool.optimal_front_run(amount)
            if front <= 0:
                profits.append(0.0)
                continue
            # Assume 1% slippage tolerance when true min_amount_out is unknown
            estimated_out = pool.quote(pool.token_x, amount)
            assumed_min_out = max(1, int(estimated_out * 0.99))
            profit, valid = pool.sandwich_profit(front, amount, assumed_min_out)
            profits.append(float(profit) if valid else 0.0)
        return float(np.mean(profits))

    def build_block(self, mempool, pool: AMMPool, block_gas_limit: int) -> list:
        """
        For each transaction (visible or encrypted):
          1. Compute E[sandwich_profit | metadata]
          2. If E[profit] > decision_threshold * gas_cost → inject speculative sandwich
             using the prior median as the estimated front-run size
          3. Fill remaining gas with high-fee user transactions

        Because the front-run size is based on an estimate, some sandwiches will be
        mis-sized: too small (leaving profit on the table) or too large (driving
        victim below their slippage tolerance → victim reverts, builder loses gas).
        At high alpha, estimates are concentrated near the prior median → consistent sizing.
        At alpha=0, estimates are spread → many mis-sized → net MEV may be negative.
        """
        txns = mempool.get_transactions()

        block = []
        gas_used = 0
        sandwich_gas = self.gas_per_txn * 3
        sandwiched_ids: set[str] = set()

        for tx in txns:
            if tx.token_in != pool.token_x:
                continue
            if gas_used + sandwich_gas > block_gas_limit:
                break
            if tx.tx_id in sandwiched_ids:
                continue

            e_profit = self.expected_sandwich_profit(tx, pool)

            if e_profit > self.decision_threshold * self.gas_per_txn:
                # Use prior median as the point estimate for the front-run
                mu, _ = self.PRIORS.get(tx.metadata_size_bucket, (6.5, 1.0))
                estimated_amount = max(1, int(np.exp(mu)))

                front = pool.optimal_front_run(estimated_amount)
                if front <= 0:
                    continue

                # Simulate to determine back-run amount
                sim = pool.fork()
                y_received = sim.swap(pool.token_x, front)

                front_txn = make_builder_txn(pool.token_x, pool.token_y, front)
                back_txn = make_builder_txn(pool.token_y, pool.token_x, y_received)

                block.append(front_txn)
                block.append(tx)
                block.append(back_txn)
                sandwiched_ids.add(tx.tx_id)
                gas_used += sandwich_gas

        # Fill remaining gas with high-fee transactions not already sandwiched
        non_mev = [
            t for t in txns
            if t.tx_id not in sandwiched_ids and t.amount_in is not None
        ]
        non_mev.sort(key=lambda t: t.gas_price, reverse=True)
        for tx in non_mev:
            if gas_used + self.gas_per_txn > block_gas_limit:
                break
            block.append(tx)
            gas_used += self.gas_per_txn

        return block
