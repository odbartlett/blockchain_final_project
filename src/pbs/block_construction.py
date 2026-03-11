"""
PBS-style block auction.

Multiple builders compete for a block slot. The highest bidder wins.
Builder bid = expected block value (MEV + fees) - margin.

See PLAN.md §10.
"""
from dataclasses import dataclass
from ..builders.base import Builder
from ..amm.pool import AMMPool


@dataclass
class BuilderBid:
    builder: Builder
    block: list          # proposed transaction ordering
    bid_amount: float    # amount offered to proposer


@dataclass
class AuctionResult:
    winner: Builder
    winning_block: list
    winning_bid: float
    all_bids: list[BuilderBid]


def run_pbs_auction(
    builders: list[Builder],
    mempool,
    pool: AMMPool,
    block_gas_limit: int,
    builder_margin: float = 0.1,   # fraction of block value kept by builder
) -> AuctionResult:
    """
    1. Each builder calls build_block() on their mempool view
    2. Each builder computes block value = MEV + total fees
    3. Bid = block_value * (1 - builder_margin)
    4. Highest bid wins
    5. Return AuctionResult with winner and all bids

    Note: all builders receive the same mempool object, but builders
    operating in encrypted/partial regimes will only see the metadata
    they are entitled to (enforced by the mempool's get_transactions()).
    """
    raise NotImplementedError  # TODO
