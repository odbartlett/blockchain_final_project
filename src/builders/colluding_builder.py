"""
Colluding Builder — information-augmenting adversary.

Pays cost c per transaction to obtain decryption from a corrupt threshold
committee member. Only purchases when expected_profit > collusion_cost.

Models incentive failures in threshold-encrypted settings.
The breakeven cost c* where net_profit = 0 is a key paper result.

See PLAN.md §7.
"""
import math
from .base import Builder, make_builder_txn
from ..amm.pool import AMMPool


# Size-bucket median estimates for quick profit screening (before decryption)
_BUCKET_MEDIANS = {
    "small":  int(math.exp(4.0)),    # ≈ 55
    "medium": int(math.exp(6.5)),    # ≈ 665
    "large":  int(math.exp(8.5)),    # ≈ 4915
}


class ColludingBuilder(Builder):
    """
    Strategy:
    1. Observe metadata-only view (EncryptedMempool)
    2. Screen each transaction using the bucket median to estimate expected profit
    3. If estimated_profit > collusion_cost_per_tx (and budget allows), purchase decryption
       via mempool.reveal_transaction() — which returns the true payload
    4. Execute sandwich using the true amount_in and min_amount_out
    5. Track net_profit = sandwich_profit - total_collusion_cost

    Key output: last_net_profit as a function of collusion_cost_per_tx.
    Zero-crossing of this curve is the minimum cost that deters collusion.
    """

    def __init__(
        self,
        collusion_cost_per_tx: float,
        budget: float,
        information_param: float = 0.0,
        gas_per_txn: float = 2.0,
    ):
        super().__init__(information_param=information_param, name="colluding")
        self.collusion_cost_per_tx = collusion_cost_per_tx
        self.budget = budget
        self.gas_per_txn = gas_per_txn

        # Tracked per build_block call — read via last_net_profit after each block
        self.last_collusion_spend: float = 0.0
        self.last_gross_mev: float = 0.0

    def _screen_profit(self, tx, pool: AMMPool) -> float:
        """
        Quick pre-purchase profit estimate from metadata alone.
        Uses bucket median as a proxy for amount_in. No pool fork needed — this is
        a fast screen to decide whether to spend collusion_cost_per_tx.
        """
        estimated_amount = _BUCKET_MEDIANS.get(tx.metadata_size_bucket, _BUCKET_MEDIANS["medium"])
        if estimated_amount <= 0:
            return 0.0
        front = pool.optimal_front_run(estimated_amount)
        if front <= 0:
            return 0.0
        # Assume 1% slippage on the estimated output
        estimated_out = pool.quote(pool.token_x, estimated_amount)
        assumed_min_out = max(1, int(estimated_out * 0.99))
        profit, valid = pool.sandwich_profit(front, estimated_amount, assumed_min_out)
        return float(profit) if valid else 0.0

    def build_block(self, mempool, pool: AMMPool, block_gas_limit: int) -> list:
        """
        Algorithm:
        1. Get metadata-only transactions from mempool
        2. For each transaction on the pool's token pair:
           a. Estimate sandwich profit from metadata (bucket median)
           b. If estimated_profit > collusion_cost_per_tx → purchase decryption
           c. Use the revealed true amount_in and min_amount_out for exact sandwich
        3. Execute all profitable (revealed) sandwiches
        4. Fill remaining gas with high-fee user transactions

        self.last_gross_mev and self.last_collusion_spend are updated here
        so that last_net_profit reflects the economic outcome of this block.
        """
        txns = mempool.get_transactions()

        block = []
        gas_used = 0
        sandwich_gas = self.gas_per_txn * 3
        sandwiched_ids: set[str] = set()
        total_collusion_spend = 0.0
        total_gross_mev = 0.0

        for tx in txns:
            if tx.token_in != pool.token_x:
                continue
            if gas_used + sandwich_gas > block_gas_limit:
                break
            if tx.tx_id in sandwiched_ids:
                continue
            if total_collusion_spend + self.collusion_cost_per_tx > self.budget:
                break

            # Screen: is this worth paying to decrypt?
            estimated_profit = self._screen_profit(tx, pool)
            if estimated_profit <= self.collusion_cost_per_tx:
                continue

            # Purchase decryption — get true payload
            revealed = mempool.reveal_transaction(tx)
            if revealed.amount_in is None or revealed.min_amount_out is None:
                continue

            # Compute exact sandwich using true amounts
            front = pool.optimal_front_run(revealed.amount_in)
            if front <= 0:
                continue

            actual_profit, valid = pool.sandwich_profit(
                front, revealed.amount_in, revealed.min_amount_out
            )
            if not valid or actual_profit <= 0:
                continue

            # Commit: charge collusion cost, record gross profit
            total_collusion_spend += self.collusion_cost_per_tx
            total_gross_mev += actual_profit

            # Build sandwich transactions
            sim = pool.fork()
            y_received = sim.swap(pool.token_x, front)

            front_txn = make_builder_txn(pool.token_x, pool.token_y, front)
            back_txn = make_builder_txn(pool.token_y, pool.token_x, y_received)

            block.append(front_txn)
            block.append(revealed)
            block.append(back_txn)
            sandwiched_ids.add(tx.tx_id)
            gas_used += sandwich_gas

        # Fill remaining gas with high-fee transactions
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

        self.last_collusion_spend = total_collusion_spend
        self.last_gross_mev = total_gross_mev
        return block

    @property
    def last_net_profit(self) -> float:
        return self.last_gross_mev - self.last_collusion_spend
