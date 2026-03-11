"""
Abstract builder interface.

See PLAN.md §4.
"""
from abc import ABC, abstractmethod
from ..amm.pool import AMMPool
from ..transaction import Transaction  # type: ignore[import]


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
        Returns total profit (in y-token units) from the builder's
        own injected transactions.

        Algorithm:
        1. Fork the pool
        2. For each transaction in block order:
           a. Execute swap against fork
           b. If tx.sender == "BUILDER", track balance delta as MEV
        3. Return sum of builder balance deltas
        """
        raise NotImplementedError  # TODO
