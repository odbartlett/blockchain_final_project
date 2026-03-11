"""
Cross-pool arbitrage detection.

See PLAN.md §9. Implement after sandwich is working.
"""
from dataclasses import dataclass
from ..amm.pool import AMMPool


@dataclass
class ArbOp:
    pool_buy: AMMPool    # buy the cheaper asset here
    pool_sell: AMMPool   # sell on the more expensive pool
    token: str
    optimal_size: int
    expected_profit: int


def find_arbitrage(pool_a: AMMPool, pool_b: AMMPool, token: str) -> ArbOp | None:
    """
    Two-pool circular arbitrage:
    - Buy token on the pool where it is cheaper
    - Sell on the pool where it is more expensive
    - Optimal size: sqrt(reserve_a_x * reserve_b_x) - reserve_a_x (harmonic mean)

    Returns None if no profitable arb exists.
    """
    raise NotImplementedError  # TODO
