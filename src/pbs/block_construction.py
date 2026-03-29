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
    PBS auction mechanism:
    1. Each builder calls build_block() on the same mempool view
    2. Compute block_value = MEV extracted + total user fees in the block
    3. Bid = block_value * (1 - builder_margin)
    4. Highest bid wins
    5. Returns AuctionResult with winner, winning block, all bids

    All builders see the same mempool object; the mempool enforces information
    restrictions via get_transactions() (e.g. EncryptedMempool redacts payloads).
    """
    bids: list[BuilderBid] = []

    for builder in builders:
        block = builder.build_block(mempool, pool.fork(), block_gas_limit)
        mev = builder.compute_mev(block, pool.fork())

        # Total user gas fees in the block (from non-BUILDER transactions)
        user_fees = sum(
            t.gas_price
            for t in block
            if getattr(t, "sender", None) != "BUILDER" and t.amount_in is not None
        )

        block_value = max(0.0, mev + user_fees)
        bid_amount = block_value * (1.0 - builder_margin)

        bids.append(BuilderBid(builder=builder, block=block, bid_amount=bid_amount))

    # Highest bid wins; tie-break by builder name for determinism
    winning_bid = max(bids, key=lambda b: (b.bid_amount, b.builder.name))

    return AuctionResult(
        winner=winning_bid.builder,
        winning_block=winning_bid.block,
        winning_bid=winning_bid.bid_amount,
        all_bids=bids,
    )
