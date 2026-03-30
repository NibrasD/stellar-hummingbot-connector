# hummingbot/connector/exchange/stellar/stellar_fill_processor.py
"""
Fill processor for the Stellar connector.
Processes trade executions (fills) and matches them to in-flight orders.
Tracks partial fills and updates order states accordingly.
"""

import logging
import time
from decimal import Decimal
from typing import Any, Callable, Dict, List, Optional, Set

from hummingbot.core.data_type.in_flight_order import InFlightOrder, OrderState, TradeUpdate
from hummingbot.core.data_type.trade_fee import AddedToCostTradeFee, TokenAmount

from .stellar_constants import STROOPS_PER_XLM

logger = logging.getLogger(__name__)


class StellarFillProcessor:
    """
    Processes trade fills from transaction results and trade streams.

    Responsibilities:
    - Parse claimed offers from ManageOffer transaction results
    - Match fills to in-flight orders
    - Track partial vs full fills
    - Calculate trade fees
    - Generate TradeUpdate events for Hummingbot
    """

    def __init__(self):
        self._processed_fills: Set[str] = set()  # Prevent duplicate processing
        self._fill_callbacks: List[Callable] = []

    def register_callback(self, callback: Callable):
        """Register a callback for when fills are processed."""
        self._fill_callbacks.append(callback)

    def process_transaction_result(
        self,
        order: InFlightOrder,
        decoded_result: Dict[str, Any],
        tx_hash: str,
    ) -> List[TradeUpdate]:
        """
        Process fills from a decoded transaction result.

        Args:
            order: The in-flight order that was submitted.
            decoded_result: Result from decode_transaction_result().
            tx_hash: The transaction hash.

        Returns:
            List of TradeUpdate objects for matched fills.
        """
        trade_updates = []
        offers_claimed = decoded_result.get("offers_claimed", [])

        if not offers_claimed:
            # No immediate fills — order is resting on the book
            logger.debug(f"Order {order.client_order_id}: No immediate fills, order resting.")
            return trade_updates

        for i, claim in enumerate(offers_claimed):
            fill_id = f"{tx_hash}_{i}"

            if fill_id in self._processed_fills:
                continue
            self._processed_fills.add(fill_id)

            amount_sold = Decimal(str(claim.get("amount_sold", 0)))
            amount_bought = Decimal(str(claim.get("amount_bought", 0)))

            if amount_sold == 0 and amount_bought == 0:
                continue

            # Determine fill price and amount based on trade type
            if order.trade_type.name == "BUY":
                fill_amount = amount_bought
                fill_price = amount_sold / amount_bought if amount_bought > 0 else Decimal(0)
            else:
                fill_amount = amount_sold
                fill_price = amount_bought / amount_sold if amount_sold > 0 else Decimal(0)

            # Stellar DEX has zero trading fees (only network fees)
            fee_charged = Decimal(str(decoded_result.get("fee_charged", 0)))
            fee_in_xlm = fee_charged / Decimal(STROOPS_PER_XLM) if fee_charged > 0 else Decimal(0)

            fee = AddedToCostTradeFee(flat_fees=[TokenAmount(token="XLM", amount=fee_in_xlm)] if fee_in_xlm > 0 else [])

            trade_update = TradeUpdate(
                trade_id=fill_id,
                client_order_id=order.client_order_id,
                exchange_order_id=str(decoded_result.get("offer_id", "")),
                trading_pair=order.trading_pair,
                fill_timestamp=time.time(),
                fill_price=fill_price,
                fill_base_amount=fill_amount,
                fill_quote_amount=fill_price * fill_amount,
                fee=fee,
            )

            trade_updates.append(trade_update)

            logger.info(f"Fill processed for {order.client_order_id}: " f"amount={fill_amount}, price={fill_price}, fee={fee_in_xlm} XLM")

        # Invoke callbacks
        for trade_update in trade_updates:
            for callback in self._fill_callbacks:
                try:
                    callback(trade_update)
                except Exception as e:
                    logger.error(f"Fill callback error: {e}")

        return trade_updates

    def process_trade_stream_event(
        self,
        trade_data: Dict[str, Any],
        in_flight_orders: Dict[str, InFlightOrder],
    ) -> Optional[TradeUpdate]:
        """
        Process a trade event from the trade stream and match it to an in-flight order.

        Args:
            trade_data: Trade data from the trade stream.
            in_flight_orders: Dict of client_order_id -> InFlightOrder.

        Returns:
            TradeUpdate if matched, None otherwise.
        """
        trade_id = trade_data.get("id", "")
        if trade_id in self._processed_fills:
            return None

        # Try to match trade to an in-flight order by exchange_order_id
        offer_id = str(trade_data.get("offer_id", ""))
        matched_order = None

        for order in in_flight_orders.values():
            if order.exchange_order_id == offer_id:
                matched_order = order
                break

        if not matched_order:
            return None

        self._processed_fills.add(trade_id)

        price_n = trade_data.get("price", {}).get("n", 0)
        price_d = trade_data.get("price", {}).get("d", 1)
        fill_price = Decimal(str(price_n)) / Decimal(str(price_d)) if price_d else Decimal(0)
        fill_amount = Decimal(str(trade_data.get("base_amount", "0")))

        fee = AddedToCostTradeFee(flat_fees=[])

        trade_update = TradeUpdate(
            trade_id=trade_id,
            client_order_id=matched_order.client_order_id,
            exchange_order_id=offer_id,
            trading_pair=matched_order.trading_pair,
            fill_timestamp=time.time(),
            fill_price=fill_price,
            fill_base_amount=fill_amount,
            fill_quote_amount=fill_price * fill_amount,
            fee=fee,
        )

        return trade_update

    def estimate_fill_status(
        self,
        order: InFlightOrder,
        total_filled: Decimal,
    ) -> OrderState:
        """
        Determines the order state based on filled amount.
        """
        if total_filled >= order.amount:
            return OrderState.FILLED
        elif total_filled > Decimal(0):
            return OrderState.PARTIALLY_FILLED
        else:
            return OrderState.OPEN

    def clear_processed(self, older_than_seconds: float = 3600):
        """
        Clears old processed fill IDs to prevent memory leaks.
        Should be called periodically.
        """
        # Simple implementation — in production, use timestamps
        if len(self._processed_fills) > 10000:
            self._processed_fills.clear()
            logger.info("Cleared processed fills cache")
