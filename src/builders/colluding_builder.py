"""
Colluding Builder — information-augmenting adversary.

Pays cost c per transaction to obtain decryption from a corrupt threshold
committee member. Only purchases when expected_profit > collusion_cost.

Models incentive failures in threshold-encrypted settings.
The breakeven cost c* where net_profit = 0 is a key paper result.

See PLAN.md §7.
"""
from .base import Builder
from ..amm.pool import AMMPool


class ColludingBuilder(Builder):
    """
    Strategy:
    1. Start with metadata-only view (EncryptedMempool)
    2. Estimate sandwich profit from metadata (uses simple heuristic or inference model)
    3. Pay collusion_cost_per_tx to reveal payload when estimated_profit > cost
    4. Execute sandwich on revealed transactions
    5. Track net_profit = sandwich_profit - collusion_cost

    Key output: net_profit as a function of collusion_cost_per_tx
    (zero-crossing = minimum deterring cost)
    """

    def __init__(
        self,
        collusion_cost_per_tx: float,
        budget: float,
        information_param: float = 0.0,
        gas_per_txn: int = 21_000,
    ):
        super().__init__(information_param=information_param, name="colluding")
        self.collusion_cost_per_tx = collusion_cost_per_tx
        self.budget = budget
        self.gas_per_txn = gas_per_txn

        # Tracked per block for analysis
        self.last_collusion_spend: float = 0.0
        self.last_gross_mev: float = 0.0

    def build_block(self, mempool, pool: AMMPool, block_gas_limit: int) -> list:
        """
        See PLAN.md §7 for full algorithm.
        Key: only purchase decryption when estimated_profit > collusion_cost_per_tx.
        """
        raise NotImplementedError  # TODO

    @property
    def last_net_profit(self) -> float:
        return self.last_gross_mev - self.last_collusion_spend
