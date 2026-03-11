"""
Unit tests for the AMM pool.

These should pass before any builder logic is written — the AMM is the
mathematical foundation of all MEV calculations.
"""
import pytest
from src.amm.pool import AMMPool


def make_pool(x=1_000_000, y=1_000_000, fee=0.003):
    return AMMPool(reserve_x=x, reserve_y=y, fee=fee, token_x="ETH", token_y="USDC")


def test_swap_maintains_invariant():
    """x * y should be non-decreasing after a swap (fees increase reserves)."""
    pool = make_pool()
    k_before = pool.reserve_x * pool.reserve_y
    pool.swap("ETH", 1000)
    k_after = pool.reserve_x * pool.reserve_y
    assert k_after >= k_before


def test_quote_does_not_mutate():
    """quote() must not change pool state."""
    pool = make_pool()
    x_before, y_before = pool.reserve_x, pool.reserve_y
    pool.quote("ETH", 1000)
    assert pool.reserve_x == x_before
    assert pool.reserve_y == y_before


def test_sandwich_invalid_when_victim_reverts():
    """Sandwich profit must be (0, False) when victim's slippage tolerance is breached."""
    pool = make_pool()
    victim_amount = 10_000
    victim_min_out = pool.quote("ETH", victim_amount)  # exact quote = 0% slippage tolerance
    # With a front-run, victim gets less than quote → should revert
    profit, valid = pool.sandwich_profit(
        front_amount=5_000,
        victim_amount=victim_amount,
        victim_min_out=victim_min_out,
    )
    assert not valid


def test_sandwich_profitable_with_loose_slippage():
    """Sandwich should be profitable when victim has 5% slippage tolerance."""
    pool = make_pool(x=10_000_000, y=10_000_000)  # deep liquidity
    victim_amount = 50_000
    victim_min_out = int(pool.quote("ETH", victim_amount) * 0.95)  # 5% tolerance
    front = pool.optimal_front_run(victim_amount)
    profit, valid = pool.sandwich_profit(front, victim_amount, victim_min_out)
    assert valid
    assert profit > 0


def test_fork_independence():
    """Mutations to a fork must not affect the original pool."""
    pool = make_pool()
    fork = pool.fork()
    fork.swap("ETH", 100_000)
    assert pool.reserve_x == 1_000_000  # original unchanged
