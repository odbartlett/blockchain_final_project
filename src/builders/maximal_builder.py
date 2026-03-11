"""
Maximal Extractor Builder — theoretical upper bound on MEV.

Under full information (I=1), finds and executes optimal sandwiches.
Under encrypted/partial information, falls back to fee-maximizing order.

See PLAN.md §6 for algorithm and closed-form formulas.
"""
from .base import Builder
from ..amm.pool import AMMPool
from ..mev.sandwich import find_sandwich_opportunities


class MaximalBuilder(Builder):
    """
    Strategy:
    1. Find all profitable sandwich opportunities (using pool.optimal_front_run)
    2. Select non-conflicting subset that fits in gas limit
    3. Fill remaining gas with highest-fee user transactions
    """

    def __init__(self, information_param: float = 1.0, gas_per_txn: int = 21_000):
        super().__init__(information_param=information_param, name="maximal")
        self.gas_per_txn = gas_per_txn

    def build_block(self, mempool, pool: AMMPool, block_gas_limit: int) -> list:
        """
        Algorithm:
        1. Get visible transactions (those with payload_visible=True)
        2. For each visible swap, compute optimal sandwich profit
        3. Sort sandwiches by profit descending
        4. Greedily add non-conflicting sandwiches (a victim tx can only be
           sandwiched once)
        5. Fill remaining gas with high-fee user txns
        6. Return ordered block: [front_run, victim, back_run, ...non_mev_txns]

        See PLAN.md §6 for optimal_front_run formula and sandwich validity check.
        """
        raise NotImplementedError  # TODO
