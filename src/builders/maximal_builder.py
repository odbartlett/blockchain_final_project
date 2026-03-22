"""
Maximal Extractor Builder — theoretical upper bound on MEV.

Under full information (I=1), finds and executes optimal sandwiches.
Under encrypted/partial information, falls back to fee-maximizing order.

See PLAN.md §6 for algorithm and closed-form formulas.
"""
import uuid
from .base import Builder
from ..amm.pool import AMMPool
from ..mempool.transaction import Transaction
from ..mev.sandwich import find_sandwich_opportunities

_GAS_PER_TXN = 21_000


def _make_builder_txn(token_in: str, token_out: str, amount_in: int) -> Transaction:
    """Create a builder-injected transaction with minimal metadata."""
    return Transaction(
        sender="BUILDER",
        token_in=token_in,
        token_out=token_out,
        amount_in=amount_in,
        min_amount_out=1,
        gas_price=0,
        deadline=10**9,
        metadata_gas_price=0,
        metadata_size_bucket="large",
        metadata_token_pair=f"{token_in}/{token_out}",
        metadata_deadline_urgency=0.0,
        payload_visible=True,
        tx_id=str(uuid.uuid4()),
    )


class MaximalBuilder(Builder):
    """
    Strategy:
    1. Find all profitable sandwich opportunities (using pool.optimal_front_run)
    2. Select non-conflicting subset that fits in gas limit
    3. Fill remaining gas with highest-fee user transactions
    """

    def __init__(self, information_param: float = 1.0, gas_per_txn: int = _GAS_PER_TXN):
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
        """
        txns = mempool.get_transactions()
        visible = [t for t in txns if t.payload_visible and t.amount_in is not None]

        # Find sandwich opportunities on a fork to avoid mutating the pool
        opportunities = find_sandwich_opportunities(visible, pool)

        block: list[Transaction] = []
        gas_used = 0
        sandwiched_ids: set[str] = set()

        # Greedily insert sandwiches (front, victim, back = 3 txns each)
        sandwich_gas = self.gas_per_txn * 3
        for op in opportunities:
            if op.victim_txn.tx_id in sandwiched_ids:
                continue
            if gas_used + sandwich_gas > block_gas_limit:
                continue

            # Compute back-run amount: simulate front-run on a fork to see
            # how much token_y the builder receives, then simulate the victim
            # to get the updated pool state, then quote the back-run.
            sim = pool.fork()
            y_received = sim.swap(pool.token_x, op.front_amount)
            sim.swap(pool.token_x, op.victim_txn.amount_in)  # victim
            # Back-run: builder sells the y_received back for token_x
            back_amount = y_received

            front_txn = _make_builder_txn(pool.token_x, pool.token_y, op.front_amount)
            back_txn = _make_builder_txn(pool.token_y, pool.token_x, back_amount)

            block.append(front_txn)
            block.append(op.victim_txn)
            block.append(back_txn)

            sandwiched_ids.add(op.victim_txn.tx_id)
            gas_used += sandwich_gas

        # Fill remaining gas with high-fee user transactions not already included
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
