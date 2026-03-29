"""
Threshold-encrypted mempool: payload hidden, metadata visible (I = 0.0).

See PLAN.md §3.
"""
import dataclasses
from .transaction import Transaction


class EncryptedMempool:
    """
    Simulates a threshold-encrypted mempool.

    amount_in, min_amount_out, and sender are withheld.
    Gas price, token pair, size bucket, and deadline urgency remain visible.
    """

    def __init__(self, transactions: list[Transaction]):
        self._txns = transactions
        self._by_id = {t.tx_id: t for t in transactions}

    def get_transactions(self) -> list[Transaction]:
        """Return transactions with payload fields redacted."""
        result = []
        for t in self._txns:
            redacted = dataclasses.replace(
                t,
                sender=None,
                amount_in=None,
                min_amount_out=None,
                payload_visible=False,
            )
            result.append(redacted)
        return result

    def reveal_transaction(self, tx: Transaction) -> Transaction:
        """Return the original unredacted transaction. Used by ColludingBuilder."""
        return self._by_id.get(tx.tx_id, tx)

    def __len__(self) -> int:
        return len(self._txns)
