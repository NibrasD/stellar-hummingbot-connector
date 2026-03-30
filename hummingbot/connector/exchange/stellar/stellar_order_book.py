# hummingbot/connector/exchange/stellar/stellar_order_book.py
"""
Stellar DEX specific OrderBook implementation.
Provides factory methods for creating order book messages from exchange data.
"""

from typing import Dict, Optional

from hummingbot.core.data_type.order_book import OrderBook
from hummingbot.core.data_type.order_book_message import OrderBookMessage, OrderBookMessageType


class StellarOrderBook(OrderBook):
    """Order book implementation for the Stellar DEX."""

    @classmethod
    def snapshot_message_from_exchange(
        cls,
        msg: Dict[str, any],
        timestamp: float,
        metadata: Optional[Dict] = None,
    ) -> OrderBookMessage:
        """Creates a snapshot message from exchange data."""
        if metadata:
            msg.update(metadata)

        update_id = msg.get("update_id", int(timestamp * 1000))

        content = {"trading_pair": msg.get("trading_pair"), "update_id": update_id, "bids": msg.get("bids", []), "asks": msg.get("asks", [])}

        return OrderBookMessage(
            message_type=OrderBookMessageType.SNAPSHOT,
            content=content,
            timestamp=timestamp,
        )

    @classmethod
    def diff_message_from_exchange(
        cls,
        msg: Dict[str, any],
        timestamp: Optional[float] = None,
        metadata: Optional[Dict] = None,
    ) -> OrderBookMessage:
        """Creates a diff message from exchange data."""
        if metadata:
            msg.update(metadata)

        update_id = msg.get("update_id", int((timestamp or 0) * 1000))

        content = {"trading_pair": msg.get("trading_pair"), "update_id": update_id, "bids": msg.get("bids", []), "asks": msg.get("asks", [])}

        return OrderBookMessage(
            message_type=OrderBookMessageType.DIFF,
            content=content,
            timestamp=timestamp,
        )

    @classmethod
    def trade_message_from_exchange(
        cls,
        msg: Dict[str, any],
        timestamp: Optional[float] = None,
        metadata: Optional[Dict] = None,
    ) -> OrderBookMessage:
        """Creates a trade message from exchange data."""
        if metadata:
            msg.update(metadata)
        return OrderBookMessage(
            message_type=OrderBookMessageType.TRADE,
            content=msg,
            timestamp=timestamp,
        )
