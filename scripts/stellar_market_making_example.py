# scripts/stellar_market_making_example.py
"""
Example script: Stellar DEX Market Making with Hummingbot.

This script demonstrates how to deploy a market-making bot on the
Stellar Decentralized Exchange using the Stellar connector.

Usage:
    1. Configure your credentials in Hummingbot: `connect stellar`
    2. Run this script: `start --script stellar_market_making_example.py`
"""

from decimal import Decimal

from hummingbot.strategy.script_strategy_base import ScriptStrategyBase


class StellarMarketMakingExample(ScriptStrategyBase):
    """
    Simple market making script for the Stellar DEX.
    Places bid and ask orders around the mid price.
    """

    # ── Configuration ──
    exchange = "stellar"
    trading_pair = "USDC-GA5ZSEJYB37JRC5AVCIA5MOP4RHTM335X2KGX3IHOJAPP5RE34K4KZVN-XLM"
    order_amount = Decimal("100")  # Amount per order
    bid_spread = Decimal("0.005")  # 0.5% below mid
    ask_spread = Decimal("0.005")  # 0.5% above mid
    order_refresh_time = 30  # Refresh every 30 seconds
    markets = {exchange: {trading_pair}}

    def __init__(self, connectors):
        super().__init__(connectors)
        self._last_refresh = 0

    def on_tick(self):
        """Called on each strategy tick."""
        if self.current_timestamp - self._last_refresh < self.order_refresh_time:
            return
        self._last_refresh = self.current_timestamp

        # Cancel all existing orders
        for order in self.get_active_orders(self.exchange):
            self.cancel(self.exchange, order.trading_pair, order.client_order_id)

        # Get current mid price
        connector = self.connectors[self.exchange]
        order_book = connector.get_order_book(self.trading_pair)
        if not order_book:
            self.logger().warning("No orderbook, skipping")
            return

        best_bid = order_book.get_price(True)
        best_ask = order_book.get_price(False)
        if not best_bid or not best_ask:
            return

        mid_price = (Decimal(str(best_bid)) + Decimal(str(best_ask))) / 2

        # Place orders
        bid_price = mid_price * (1 - self.bid_spread)
        ask_price = mid_price * (1 + self.ask_spread)

        self.buy(self.exchange, self.trading_pair, self.order_amount, OrderType.LIMIT, bid_price)
        self.sell(self.exchange, self.trading_pair, self.order_amount, OrderType.LIMIT, ask_price)

        self.logger().info(
            f"📊 Market Making: BID {self.order_amount} @ {bid_price:.7f} | " f"ASK {self.order_amount} @ {ask_price:.7f} | " f"MID: {mid_price:.7f}"
        )

    def format_status(self) -> str:
        lines = ["", "  Stellar Market Maker Example"]
        lines.append(f"  Pair: {self.trading_pair}")
        lines.append(f"  Spread: {self.bid_spread:.2%} / {self.ask_spread:.2%}")
        lines.append(f"  Amount: {self.order_amount}")
        active = self.get_active_orders(self.exchange)
        lines.append(f"  Active Orders: {len(active)}")
        return "\n".join(lines)
