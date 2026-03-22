"""
Constant-product AMM (x * y = k) with fee.

See PLAN.md §1 for full implementation spec.
"""
import copy
import math
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
        """Spot price of token_x in terms of token_y (y per x)."""
        return self.reserve_y / self.reserve_x

    def swap(self, token_in: str, amount_in: int) -> int:
        """
        Execute a swap. Returns amount_out. Mutates pool state.

        Formula: amount_out = (amount_in * (1-fee) * reserve_out)
                              / (reserve_in + amount_in * (1-fee))
        """
        if token_in == self.token_x:
            reserve_in = self.reserve_x
            reserve_out = self.reserve_y
        elif token_in == self.token_y:
            reserve_in = self.reserve_y
            reserve_out = self.reserve_x
        else:
            raise ValueError(f"Unknown token: {token_in}")

        amount_in_with_fee = amount_in * (1 - self.fee)
        amount_out = int(amount_in_with_fee * reserve_out / (reserve_in + amount_in_with_fee))

        if token_in == self.token_x:
            self.reserve_x += amount_in
            self.reserve_y -= amount_out
        else:
            self.reserve_y += amount_in
            self.reserve_x -= amount_out

        return amount_out

    def quote(self, token_in: str, amount_in: int) -> int:
        """Same as swap but does NOT mutate state. Safe for planning."""
        fork = self.fork()
        return fork.swap(token_in, amount_in)

    def price_impact(self, token_in: str, amount_in: int) -> float:
        """Fractional price shift after swap: (price_after / price_before) - 1."""
        price_before = self.get_price()
        fork = self.fork()
        fork.swap(token_in, amount_in)
        price_after = fork.get_price()
        return price_after / price_before - 1.0

    def sandwich_profit(
        self,
        front_amount: int,
        victim_amount: int,
        victim_min_out: int,
    ) -> tuple[int, bool]:
        """
        Simulate a sandwich: front-run, victim, back-run.
        Returns (net_profit_in_token_x, victim_satisfied).

        Sequence (builder buys token_x with token_y):
          1. Front-run: builder swaps token_y -> token_x (front_amount of token_y in)
          2. Victim: swaps token_x -> token_y (victim_amount of token_x in)
          3. Back-run: builder swaps token_x -> token_y (all token_x received in step 1)

        victim_satisfied is False if victim's min_amount_out is not met
        (sandwich would cause victim to revert — INVALID).

        See PLAN.md §6 for the closed-form optimal front_amount formula.
        """
        fork = self.fork()

        # Step 1: builder front-runs by buying token_x (spending token_y)
        # front_amount is denominated in token_x terms (how much x we want to shift)
        # Per PLAN.md the formula assumes front_amount is the token_x input analog.
        # We implement: builder sends front_amount of token_x's pair (token_y side analog)
        # Actually, in sandwich attacks the builder front-runs in the SAME direction as
        # the victim. Victim is swapping token_x -> token_y, so builder also swaps
        # token_x -> token_y first. Builder spends front_amount of token_x.

        # Front-run: builder buys token_y by selling front_amount of token_x
        builder_y_received_front = fork.swap(fork.token_x, front_amount)

        # Victim swap: victim swaps token_x -> token_y
        victim_out = fork.swap(fork.token_x, victim_amount)
        victim_satisfied = victim_out >= victim_min_out

        if not victim_satisfied:
            return 0, False

        # Back-run: builder sells the token_y back for token_x
        # Builder received builder_y_received_front of token_y during front-run
        # Now swaps that back to token_x
        builder_x_received_back = fork.swap(fork.token_y, builder_y_received_front)

        # Net profit in token_x: received token_x back minus what was spent
        net_profit = builder_x_received_back - front_amount
        return net_profit, True

    def optimal_front_run(self, victim_amount: int) -> int:
        """
        Closed-form optimal front-run size for a constant-product AMM:
            f* = sqrt(reserve_x * (reserve_x + victim_amount)) - reserve_x

        See PLAN.md §6.
        """
        f_star = math.sqrt(self.reserve_x * (self.reserve_x + victim_amount)) - self.reserve_x
        return max(0, int(f_star))

    def fork(self) -> "AMMPool":
        """Return a deep copy for speculative simulation."""
        return copy.deepcopy(self)
