"""
Transaction data model.

See PLAN.md §2 for full field spec and visibility semantics.
"""
import uuid
from dataclasses import dataclass, field


@dataclass
class Transaction:
    """
    A pending user transaction.

    In encrypted mempools, payload fields (amount_in, min_amount_out, sender)
    are set to None. Metadata fields are always visible.
    """
    # Payload fields (hidden in encrypted regime)
    sender: str | None
    token_in: str
    token_out: str
    amount_in: int | None          # base units; None when encrypted
    min_amount_out: int | None     # slippage bound; None when encrypted
    gas_price: int
    deadline: int                  # block number

    # Metadata (always public — leaks even in threshold-encrypted mempools)
    metadata_gas_price: int        # same as gas_price; always visible
    metadata_size_bucket: str      # "small" | "medium" | "large"
    metadata_token_pair: str       # e.g. "ETH/USDC"
    metadata_deadline_urgency: float  # 0 (far future) to 1 (imminent)

    # Visibility flag set by the mempool regime
    payload_visible: bool = True

    tx_id: str = field(default_factory=lambda: str(uuid.uuid4()))

    @classmethod
    def from_visible(
        cls,
        sender: str,
        token_in: str,
        token_out: str,
        amount_in: int,
        min_amount_out: int,
        gas_price: int,
        deadline: int,
        current_block: int,
        size_thresholds: tuple[int, int] = (500, 5000),
    ) -> "Transaction":
        """
        Construct a fully visible transaction with auto-computed metadata.
        size_thresholds: (small_max, medium_max) in base units.
        """
        raise NotImplementedError  # TODO: compute metadata fields and return instance
