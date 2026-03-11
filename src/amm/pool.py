"""
Constant-product AMM (x * y = k) with fee.

See PLAN.md §1 for full implementation spec.
"""
import copy
from dataclasses import dataclass


@dataclass
class AMMPool:
    """
    Constant-product AMM with multiplicative fee.

    Reserves are stored as integers (base units) to avoid float rounding.
    fee is a float in [0, 1), e.g. 0.003 for 0.3%.
    """
    reserve_x: int
    reserve_y: int
    fee: float = 0.003
    token_x: str = "ETH"
    token_y: str = "USDC"

    def get_price(self) -> float:
        """Spot price of token_x in terms of token_y."""
        raise NotImplementedError  # TODO

    def swap(self, token_in: str, amount_in: int) -> int:
        """
        Execute a swap. Returns amount_out. Mutates pool state.

        Formula: amount_out = (amount_in * (1-fee) * reserve_out)
                              / (reserve_in + amount_in * (1-fee))
        """
        raise NotImplementedError  # TODO

    def quote(self, token_in: str, amount_in: int) -> int:
        """Same as swap but does NOT mutate state. Safe for planning."""
        fork = self.fork()
        return fork.swap(token_in, amount_in)

    def price_impact(self, token_in: str, amount_in: int) -> float:
        """Fractional price shift after swap (before / after - 1)."""
        raise NotImplementedError  # TODO

    def sandwich_profit(
        self,
        front_amount: int,
        victim_amount: int,
        victim_min_out: int,
    ) -> tuple[int, bool]:
        """
        Simulate a sandwich: front-run, victim, back-run.
        Returns (net_profit_in_y, victim_satisfied).

        victim_satisfied is False if victim's min_amount_out is not met
        (sandwich would cause victim to revert — INVALID).

        See PLAN.md §6 for the closed-form optimal front_amount formula.
        """
        raise NotImplementedError  # TODO

    def optimal_front_run(self, victim_amount: int) -> int:
        """
        Closed-form optimal front-run size for a constant-product AMM:
            f* = sqrt(reserve_x * (reserve_x + victim_amount)) - reserve_x

        See PLAN.md §6.
        """
        raise NotImplementedError  # TODO

    def fork(self) -> "AMMPool":
        """Return a deep copy for speculative simulation."""
        return copy.deepcopy(self)
