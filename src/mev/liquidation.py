"""
Liquidation MEV detection. Stub — implement after sandwich/arb.

See PLAN.md §9.
"""
from dataclasses import dataclass
from ..amm.pool import AMMPool


@dataclass
class Position:
    owner: str
    collateral_token: str
    collateral_amount: int
    debt_token: str
    debt_amount: int
    liquidation_threshold: float   # e.g. 1.5 = must maintain 150% collateral ratio


@dataclass
class LiquidationOp:
    position: Position
    expected_profit: int


def find_liquidations(positions: list[Position], pool: AMMPool) -> list[LiquidationOp]:
    """
    A position is liquidatable when:
        collateral_value / debt_value < liquidation_threshold

    At current pool price: collateral_value = collateral_amount * spot_price
    Returns profitable liquidation ops sorted by profit descending.
    """
    raise NotImplementedError  # TODO
