"""
Sandwich attack primitives.

See PLAN.md §9.
"""
from dataclasses import dataclass
from ..amm.pool import AMMPool
from ..mempool.transaction import Transaction


@dataclass
class SandwichOp:
    victim_txn: Transaction
    front_amount: int      # amount of token_x to swap before victim
    expected_profit: int   # net profit in token_x units
    valid: bool            # False if victim would revert


def find_sandwich_opportunities(
    txns: list[Transaction],
    pool: AMMPool,
) -> list[SandwichOp]:
    """
    Scan a list of transactions for sandwichable swaps.

    A transaction is sandwichable iff:
    - payload_visible = True (amount_in and min_amount_out are known)
    - It is a swap on the given pool's token pair (token_in == pool.token_x)
    - sandwich_profit(optimal_front_run, victim.amount_in) > 0
    - The victim's min_amount_out is satisfied after the front-run

    Returns list of SandwichOp, sorted by expected_profit descending.
    """
    opportunities = []
    for tx in txns:
        if not tx.payload_visible:
            continue
        if tx.amount_in is None or tx.min_amount_out is None:
            continue
        # Only sandwich swaps in the direction the pool supports
        if tx.token_in != pool.token_x:
            continue

        front = pool.optimal_front_run(tx.amount_in)
        if front <= 0:
            continue

        profit, valid = pool.sandwich_profit(front, tx.amount_in, tx.min_amount_out)
        if valid and profit > 0:
            opportunities.append(SandwichOp(
                victim_txn=tx,
                front_amount=front,
                expected_profit=profit,
                valid=True,
            ))

    opportunities.sort(key=lambda op: op.expected_profit, reverse=True)
    return opportunities


def execute_sandwich(
    pool: AMMPool,
    front_amount: int,
    victim_txn: Transaction,
) -> tuple[int, bool]:
    """
    Execute sandwich on a pool fork. Returns (net_profit_in_token_x, victim_satisfied).

    Does NOT mutate pool — operates on a fork internally.
    Sequence: front-run swap → victim swap → back-run swap (reverse direction).
    """
    if victim_txn.amount_in is None or victim_txn.min_amount_out is None:
        return 0, False

    return pool.sandwich_profit(front_amount, victim_txn.amount_in, victim_txn.min_amount_out)
