"""
Partial-information mempool: metadata leakage with optional noise (I ∈ (0,1)).

See PLAN.md §3 for the mapping between I, leakage_rate, and noise_sigma.
"""
import dataclasses
import random
from .transaction import Transaction


class PartialMempool:
    """
    Each transaction is revealed with probability leakage_rate.
    Non-revealed transactions expose only metadata + a noisy amount estimate.

    Mapping to information parameter I:
        I ≈ leakage_rate  (see PLAN.md for formal definition)

    Args:
        transactions:   Raw (fully visible) transactions
        leakage_rate:   Probability ∈ [0,1] that a transaction is fully revealed
        noise_sigma:    Relative std-dev of noisy amount estimate (e.g. 0.3 = ±30%)
        rng:            Optional seeded random.Random for reproducibility
    """

    def __init__(
        self,
        transactions: list[Transaction],
        leakage_rate: float,
        noise_sigma: float = 0.3,
        rng: random.Random | None = None,
    ):
        self._txns = transactions
        self.leakage_rate = leakage_rate
        self.noise_sigma = noise_sigma
        self._rng = rng or random.Random()

    def get_transactions(self) -> list[Transaction]:
        """
        Return transactions with probabilistic payload exposure.

        For revealed transactions: payload_visible=True, exact amount_in.
        For hidden transactions: payload_visible=False,
            amount_in = noisy estimate drawn from N(true, noise_sigma * true),
            clamped to >= 1.
        """
        result = []
        for t in self._txns:
            if self._rng.random() < self.leakage_rate:
                # Fully revealed
                result.append(dataclasses.replace(t, payload_visible=True))
            else:
                # Metadata only; noisy amount estimate
                true_amount = t.amount_in or 0
                noise = self._rng.gauss(0, self.noise_sigma * true_amount)
                noisy_amount = max(1, int(true_amount + noise))
                result.append(dataclasses.replace(
                    t,
                    sender=None,
                    amount_in=noisy_amount,
                    min_amount_out=None,
                    payload_visible=False,
                ))
        return result

    def __len__(self) -> int:
        return len(self._txns)
