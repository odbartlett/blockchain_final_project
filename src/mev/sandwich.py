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
    front_amount: int      # amount to swap before victim
    expected_profit: int   # net profit in y-token units
    valid: bool            # False if victim would revert


def find_sandwich_opportunities(
    txns: list[Transaction],
    pool: AMMPool,
) -> list[SandwichOp]:
    """
    Scan a list of transactions for sandwichable swaps.

    A transaction is sandwichable iff:
    - payload_visible = True (amount_in and min_amount_out are known)
    - It is a swap on the given pool's token pair
    - sandwich_profit(optimal_front_run, victim.amount_in) > 0
    - The victim's min_amount_out is satisfied after the front-run

    Returns list of SandwichOp, sorted by expected_profit descending.
    """
    raise NotImplementedError  # TODO


def execute_sandwich(
    pool: AMMPool,
    front_amount: int,
    victim_txn: Transaction,
) -> tuple[int, bool]:
    """
    Execute sandwich on a pool fork. Returns (net_profit, victim_satisfied).

    Does NOT mutate pool — caller should apply to a fork.
    Sequence: front-run swap → victim swap → back-run swap (reverse direction).
    """
    raise NotImplementedError  # TODO
