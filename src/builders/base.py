"""
Abstract builder interface.

See PLAN.md §4.
"""
import uuid
from abc import ABC, abstractmethod
from ..amm.pool import AMMPool
from ..mempool.transaction import Transaction


def make_builder_txn(token_in: str, token_out: str, amount_in: int) -> Transaction:
    """Create a builder-injected transaction with sentinel sender='BUILDER'."""
    return Transaction(
        sender="BUILDER",
        token_in=token_in,
        token_out=token_out,
        amount_in=amount_in,
        min_amount_out=1,
        gas_price=0,
        deadline=10**9,
        metadata_gas_price=0,
        metadata_size_bucket="large",
        metadata_token_pair=f"{token_in}/{token_out}",
        metadata_deadline_urgency=0.0,
        payload_visible=True,
        tx_id=str(uuid.uuid4()),
    )


class Builder(ABC):
    """
    Base class for all PBS block builders.

    Subclasses implement build_block() with their adversarial strategy.
    compute_mev() is shared: it replays the block against a pool fork
    and tracks the builder's own injected transactions.
    """

    def __init__(self, information_param: float, name: str = "builder"):
        self.information_param = information_param
        self.name = name

    @abstractmethod
    def build_block(
        self,
        mempool,           # PublicMempool | EncryptedMempool | PartialMempool
        pool: AMMPool,
        block_gas_limit: int,
    ) -> list:             # list[Transaction]
        """
        Return an ordered list of transactions forming the proposed block.
        May include injected transactions (front-runs, back-runs).
        Must respect block_gas_limit.
        """
        ...

    def compute_mev(self, block: list, pool: AMMPool) -> float:
        """
        Execute the block sequentially against a pool fork.
        Returns total profit (in token_x units) from the builder's
        own injected transactions (sender == "BUILDER").

        Tracks the builder's wallet:
          - When builder spends token_x: wallet_x -= amount_in
          - When builder receives token_x: wallet_x += amount_out
          - Same for token_y
        Final MEV = wallet_x + wallet_y * (reserve_x / reserve_y)
        """
        fork = pool.fork()
        wallet_x: float = 0.0
        wallet_y: float = 0.0

        for tx in block:
            if tx.amount_in is None:
                continue
            amount_out = fork.swap(tx.token_in, tx.amount_in)

            if getattr(tx, "sender", None) == "BUILDER":
                if tx.token_in == fork.token_x:
                    wallet_x -= tx.amount_in
                    wallet_y += amount_out
                else:
                    wallet_y -= tx.amount_in
                    wallet_x += amount_out

        # Convert any remaining token_y balance to token_x at current pool price
        if fork.reserve_y > 0:
            wallet_x += wallet_y * fork.reserve_x / fork.reserve_y
        return wallet_x
