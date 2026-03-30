# hummingbot/connector/exchange/stellar/stellar_order_placement_strategy.py
"""
Order placement strategy for the Stellar connector.
Handles smart order placement with retry logic, fee bumping,
and batch operations.
"""

import logging
from decimal import Decimal
from typing import Any, Dict, List

from stellar_sdk import Asset

from .stellar_auth import StellarAuth
from .stellar_client import StellarClient
from .stellar_transaction_pipeline import StellarTransactionPipeline, TransactionRequest
from .stellar_xdr_utils import build_cancel_offer_op, build_manage_buy_offer_op, build_manage_sell_offer_op

logger = logging.getLogger(__name__)


class StellarOrderPlacementStrategy:
    """
    Implements smart order placement for the Stellar DEX.

    Features:
    - Single order placement with retry
    - Batch order placement (multiple ops in one transaction)
    - Batch cancellation
    - Cancel-and-replace in a single transaction (atomic)
    - Automatic fee bumping on tx_insufficient_fee errors
    """

    def __init__(
        self,
        auth: StellarAuth,
        client: StellarClient,
        pipeline: StellarTransactionPipeline,
    ):
        self._auth = auth
        self._client = client
        self._pipeline = pipeline

    async def place_order(
        self,
        request_id: str,
        selling: Asset,
        buying: Asset,
        amount: Decimal,
        price: Decimal,
        is_buy: bool = True,
        offer_id: int = 0,
        callback=None,
    ) -> str:
        """
        Places a single order on the Stellar DEX.

        Args:
            request_id: Unique ID for this order request.
            selling: Asset to sell.
            buying: Asset to buy.
            amount: Amount to trade.
            price: Price per unit.
            is_buy: Whether this is a buy or sell from the user's perspective.
            offer_id: Existing offer ID to modify (0 = new order).
            callback: Async callback invoked with the TransactionRequest result.

        Returns:
            The request ID for tracking.
        """
        if is_buy:
            op = build_manage_buy_offer_op(
                selling=selling,
                buying=buying,
                amount=str(amount),
                price=str(price),
                offer_id=offer_id,
            )
        else:
            op = build_manage_sell_offer_op(
                selling=selling,
                buying=buying,
                amount=str(amount),
                price=str(price),
                offer_id=offer_id,
            )

        tx_request = TransactionRequest(
            request_id=request_id,
            operations=[op],
            callback=callback,
            memo=f"hbot_{request_id[:8]}",
        )

        return await self._pipeline.submit(tx_request)

    async def cancel_order(
        self,
        request_id: str,
        selling: Asset,
        buying: Asset,
        offer_id: int,
        callback=None,
    ) -> str:
        """
        Cancels an existing order on the Stellar DEX.
        """
        op = build_cancel_offer_op(
            selling=selling,
            buying=buying,
            offer_id=offer_id,
        )

        tx_request = TransactionRequest(
            request_id=f"cancel_{request_id}",
            operations=[op],
            callback=callback,
            memo=f"cancel_{request_id[:6]}",
        )

        return await self._pipeline.submit(tx_request)

    async def batch_place_orders(
        self,
        orders: List[Dict[str, Any]],
        request_id: str,
        callback=None,
    ) -> str:
        """
        Places multiple orders in a single transaction (atomic).

        Each order dict should have:
        - selling: Asset
        - buying: Asset
        - amount: Decimal
        - price: Decimal
        - is_buy: bool
        """
        operations = []
        for order in orders:
            if order.get("is_buy", True):
                op = build_manage_buy_offer_op(
                    selling=order["selling"],
                    buying=order["buying"],
                    amount=str(order["amount"]),
                    price=str(order["price"]),
                )
            else:
                op = build_manage_sell_offer_op(
                    selling=order["selling"],
                    buying=order["buying"],
                    amount=str(order["amount"]),
                    price=str(order["price"]),
                )
            operations.append(op)

        tx_request = TransactionRequest(
            request_id=request_id,
            operations=operations,
            callback=callback,
            memo=f"batch_{len(operations)}",
        )

        return await self._pipeline.submit(tx_request)

    async def batch_cancel_orders(
        self,
        cancellations: List[Dict[str, Any]],
        request_id: str,
        callback=None,
    ) -> str:
        """
        Cancels multiple orders in a single transaction (atomic).

        Each cancellation dict should have:
        - selling: Asset
        - buying: Asset
        - offer_id: int
        """
        operations = []
        for cancel in cancellations:
            op = build_cancel_offer_op(
                selling=cancel["selling"],
                buying=cancel["buying"],
                offer_id=cancel["offer_id"],
            )
            operations.append(op)

        tx_request = TransactionRequest(
            request_id=f"batch_cancel_{request_id}",
            operations=operations,
            callback=callback,
            memo="batch_cancel",
        )

        return await self._pipeline.submit(tx_request)

    async def cancel_and_replace(
        self,
        old_offer_ids: List[Dict[str, Any]],
        new_orders: List[Dict[str, Any]],
        request_id: str,
        callback=None,
    ) -> str:
        """
        Atomically cancels old orders and places new ones in a single transaction.
        This is the most efficient way to update market-making orders.

        Args:
            old_offer_ids: List of dicts with {selling, buying, offer_id}
            new_orders: List of dicts with {selling, buying, amount, price, is_buy}
            request_id: Unique request ID.
            callback: Result callback.
        """
        operations = []

        # First, cancel old orders
        for cancel in old_offer_ids:
            op = build_cancel_offer_op(
                selling=cancel["selling"],
                buying=cancel["buying"],
                offer_id=cancel["offer_id"],
            )
            operations.append(op)

        # Then, place new orders
        for order in new_orders:
            if order.get("is_buy", True):
                op = build_manage_buy_offer_op(
                    selling=order["selling"],
                    buying=order["buying"],
                    amount=str(order["amount"]),
                    price=str(order["price"]),
                )
            else:
                op = build_manage_sell_offer_op(
                    selling=order["selling"],
                    buying=order["buying"],
                    amount=str(order["amount"]),
                    price=str(order["price"]),
                )
            operations.append(op)

        tx_request = TransactionRequest(
            request_id=request_id,
            operations=operations,
            callback=callback,
            memo="replace",
        )

        return await self._pipeline.submit(tx_request)
