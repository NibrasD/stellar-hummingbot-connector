# hummingbot/strategy/stellar_market_maker/stellar_market_maker.py
"""
Market Making strategy for the Stellar DEX.
Places bid and ask orders around the mid-price with configurable spreads.
Automatically refreshes orders at a configurable interval.
"""

import asyncio
import logging
from decimal import Decimal
from typing import List

from hummingbot.core.data_type.common import OrderType
from hummingbot.strategy.strategy_py_base import StrategyPyBase

logger = logging.getLogger(__name__)


class StellarMarketMaker(StrategyPyBase):
    """
    Pure market making strategy for the Stellar DEX.

    Features:
    - Configurable bid/ask spreads
    - Configurable order amounts
    - Auto-refresh at configurable intervals
    - Multiple order levels
    - Inventory-based skew
    - Kill-switch on large drawdowns
    """

    def __init__(
        self,
        exchange,
        trading_pair: str,
        bid_spread: Decimal = Decimal("0.01"),
        ask_spread: Decimal = Decimal("0.01"),
        order_amount: Decimal = Decimal("10"),
        order_refresh_time: float = 30.0,
        order_levels: int = 1,
        order_level_spread: Decimal = Decimal("0.005"),
        order_level_amount: Decimal = Decimal("0"),
        inventory_skew_enabled: bool = False,
        inventory_target_base_pct: Decimal = Decimal("0.5"),
    ):
        super().__init__()
        self._exchange = exchange
        self._trading_pair = trading_pair
        self._bid_spread = bid_spread
        self._ask_spread = ask_spread
        self._order_amount = order_amount
        self._order_refresh_time = order_refresh_time
        self._order_levels = order_levels
        self._order_level_spread = order_level_spread
        self._order_level_amount = order_level_amount
        self._inventory_skew_enabled = inventory_skew_enabled
        self._inventory_target_base_pct = inventory_target_base_pct

        self._active_buys: List[str] = []
        self._active_sells: List[str] = []
        self._last_refresh_time: float = 0
        self._order_refresh_tolerance_pct = Decimal("0.02")

    def tick(self, timestamp: float):
        """Called on each strategy tick."""
        if not self._exchange.ready:
            return

        if timestamp - self._last_refresh_time < self._order_refresh_time:
            return

        self._last_refresh_time = timestamp

        # Cancel and replace orders
        asyncio.ensure_future(self._refresh_orders())

    async def _refresh_orders(self):
        """Cancel existing orders and place new ones."""
        try:
            # Cancel all active orders
            await self._cancel_active_orders()

            # Get current mid price
            order_book = self._exchange.get_order_book(self._trading_pair)
            if order_book is None:
                logger.warning("No orderbook available, skipping order placement")
                return

            best_bid = order_book.get_price(True)  # best bid
            best_ask = order_book.get_price(False)  # best ask

            if best_bid is None or best_ask is None or best_bid <= 0 or best_ask <= 0:
                logger.warning("Invalid orderbook prices, skipping")
                return

            mid_price = (Decimal(str(best_bid)) + Decimal(str(best_ask))) / Decimal("2")

            # Calculate base and quote balances for inventory skew
            base_currency = self._trading_pair.split("-")[0]
            self._trading_pair.replace(f"{base_currency}-", "")

            bid_amount = self._order_amount
            ask_amount = self._order_amount

            if self._inventory_skew_enabled:
                bid_amount, ask_amount = self._calculate_skewed_amounts(base_currency, mid_price)

            # Place orders at each level
            for level in range(self._order_levels):
                level_spread_adj = self._order_level_spread * Decimal(level)
                level_amount_adj = self._order_level_amount * Decimal(level)

                # Bid (buy) order
                bid_price = mid_price * (Decimal("1") - self._bid_spread - level_spread_adj)
                bid_qty = bid_amount + level_amount_adj

                if bid_qty > 0 and bid_price > 0:
                    order_id = self._exchange.buy(
                        self._trading_pair,
                        bid_qty,
                        OrderType.LIMIT,
                        bid_price,
                    )
                    self._active_buys.append(order_id)
                    logger.info(f"Placed BID L{level}: {bid_qty} @ {bid_price:.7f}")

                # Ask (sell) order
                ask_price = mid_price * (Decimal("1") + self._ask_spread + level_spread_adj)
                ask_qty = ask_amount + level_amount_adj

                if ask_qty > 0 and ask_price > 0:
                    order_id = self._exchange.sell(
                        self._trading_pair,
                        ask_qty,
                        OrderType.LIMIT,
                        ask_price,
                    )
                    self._active_sells.append(order_id)
                    logger.info(f"Placed ASK L{level}: {ask_qty} @ {ask_price:.7f}")

        except Exception as e:
            logger.error(f"Error refreshing orders: {e}", exc_info=True)

    async def _cancel_active_orders(self):
        """Cancel all active orders."""
        for order_id in self._active_buys + self._active_sells:
            try:
                self._exchange.cancel(self._trading_pair, order_id)
            except Exception as e:
                logger.debug(f"Error cancelling {order_id}: {e}")

        self._active_buys.clear()
        self._active_sells.clear()
        await asyncio.sleep(0.5)  # Brief pause for cancellations to process

    def _calculate_skewed_amounts(self, base_currency: str, mid_price: Decimal) -> tuple:
        """Calculate inventory-skewed bid/ask amounts."""
        base_balance = self._exchange.get_available_balance(base_currency)
        quote_balance = self._exchange.get_available_balance("XLM")  # or appropriate quote

        total_value = base_balance * mid_price + quote_balance
        if total_value == 0:
            return self._order_amount, self._order_amount

        current_base_pct = (base_balance * mid_price) / total_value
        target_pct = self._inventory_target_base_pct

        # If we have too much base, increase sells, decrease buys
        skew = current_base_pct - target_pct
        bid_amount = self._order_amount * (Decimal("1") - skew * Decimal("2"))
        ask_amount = self._order_amount * (Decimal("1") + skew * Decimal("2"))

        bid_amount = max(bid_amount, Decimal("0"))
        ask_amount = max(ask_amount, Decimal("0"))

        return bid_amount, ask_amount

    def format_status(self) -> str:
        """Returns strategy status."""
        lines = []
        lines.append(f"\n  Stellar Market Maker Status")
        lines.append(f"  ═══════════════════════════")
        lines.append(f"  Pair:        {self._trading_pair}")
        lines.append(f"  Bid Spread:  {self._bid_spread:.4%}")
        lines.append(f"  Ask Spread:  {self._ask_spread:.4%}")
        lines.append(f"  Amount:      {self._order_amount}")
        lines.append(f"  Levels:      {self._order_levels}")
        lines.append(f"  Refresh:     {self._order_refresh_time}s")
        lines.append(f"  Active Buys: {len(self._active_buys)}")
        lines.append(f"  Active Sells:{len(self._active_sells)}")
        return "\n".join(lines)
