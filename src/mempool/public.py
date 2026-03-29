"""
Public mempool: full payload visibility (I = 1.0).

See PLAN.md §3.
"""
from .transaction import Transaction


class PublicMempool:
    """All transactions are fully visible."""

    def __init__(self, transactions: list[Transaction]):
        self._txns = transactions

    def get_transactions(self) -> list[Transaction]:
        """Return all transactions with payload_visible=True."""
        for t in self._txns:
            t.payload_visible = True
        return list(self._txns)

    def reveal_transaction(self, tx: Transaction) -> Transaction:
        """Return fully visible transaction (already public)."""
        return tx

    def __len__(self) -> int:
        return len(self._txns)
