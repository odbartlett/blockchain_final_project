"""
Random Builder — baseline control.

Orders valid transactions randomly. Extracts no intentional MEV.
Any MEV measured from this builder reflects structural/random effects
and provides the zero-baseline for the experiment.

See PLAN.md §5.
"""
import random
from .base import Builder
from ..amm.pool import AMMPool


class RandomBuilder(Builder):
    """
    Packs transactions in random order up to block_gas_limit.
    Does NOT inject any front-run or back-run transactions.
    """

    def __init__(self, rng: random.Random | None = None):
        super().__init__(information_param=0.0, name="random")
        self._rng = rng or random.Random()

    def build_block(self, mempool, pool: AMMPool, block_gas_limit: int) -> list:
        """
        1. Get all transactions from mempool
        2. Shuffle randomly
        3. Greedily pack until gas limit reached
        4. Return packed list (no injected txns)
        """
        txns = mempool.get_transactions()
        self._rng.shuffle(txns)

        block = []
        gas_used = 0
        gas_per_txn = 21_000

        for tx in txns:
            if tx.amount_in is None:
                continue
            if gas_used + gas_per_txn > block_gas_limit:
                break
            block.append(tx)
            gas_used += gas_per_txn

        return block
