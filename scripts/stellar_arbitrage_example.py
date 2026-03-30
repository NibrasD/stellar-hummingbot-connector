# scripts/stellar_arbitrage_example.py
"""
Example script: Cross-DEX Arbitrage on Stellar.

This script demonstrates arbitrage between the Stellar DEX orderbook
and external exchanges (or between different Stellar AMMs).

Usage:
    1. Configure both connectors in Hummingbot
    2. Run: `start --script stellar_arbitrage_example.py`
"""

from decimal import Decimal

from hummingbot.strategy.script_strategy_base import ScriptStrategyBase


class StellarArbitrageExample(ScriptStrategyBase):
    """
    Arbitrage between Stellar DEX and another exchange.
    Monitors price discrepancies and executes when profitable.
    """

    # ── Configuration ──
    stellar_exchange = "stellar"
    other_exchange = "binance"  # Or another Stellar AMM connector
    trading_pair_stellar = "XLM-USDC-GA5ZSEJYB37JRC5AVCIA5MOP4RHTM335X2KGX3IHOJAPP5RE34K4KZVN"
    trading_pair_other = "XLM-USDT"
    min_profitability = Decimal("0.003")  # 0.3% minimum
    order_amount = Decimal("500")
    check_interval = 5  # seconds

    markets = {
        stellar_exchange: {trading_pair_stellar},
        other_exchange: {trading_pair_other},
    }

    def __init__(self, connectors):
        super().__init__(connectors)
        self._last_check = 0
        self._total_arb_profits = Decimal("0")

    def on_tick(self):
        if self.current_timestamp - self._last_check < self.check_interval:
            return
        self._last_check = self.current_timestamp

        stellar = self.connectors[self.stellar_exchange]
        other = self.connectors[self.other_exchange]

        ob_stellar = stellar.get_order_book(self.trading_pair_stellar)
        ob_other = other.get_order_book(self.trading_pair_other)

        if not ob_stellar or not ob_other:
            return

        stellar_bid = Decimal(str(ob_stellar.get_price(True) or 0))
        stellar_ask = Decimal(str(ob_stellar.get_price(False) or 0))
        other_bid = Decimal(str(ob_other.get_price(True) or 0))
        other_ask = Decimal(str(ob_other.get_price(False) or 0))

        if not all([stellar_bid, stellar_ask, other_bid, other_ask]):
            return

        # Buy stellar, sell other
        profit_st_to_ot = (other_bid - stellar_ask) / stellar_ask
        if profit_st_to_ot > self.min_profitability:
            self.logger().info(f"🔄 ARB: Buy Stellar@{stellar_ask:.6f} → Sell Other@{other_bid:.6f} " f"Profit: {profit_st_to_ot:.4%}")
            self.buy(self.stellar_exchange, self.trading_pair_stellar, self.order_amount, OrderType.LIMIT, stellar_ask)
            self.sell(self.other_exchange, self.trading_pair_other, self.order_amount, OrderType.LIMIT, other_bid)
            self._total_arb_profits += profit_st_to_ot * self.order_amount

        # Buy other, sell stellar
        profit_ot_to_st = (stellar_bid - other_ask) / other_ask
        if profit_ot_to_st > self.min_profitability:
            self.logger().info(f"🔄 ARB: Buy Other@{other_ask:.6f} → Sell Stellar@{stellar_bid:.6f} " f"Profit: {profit_ot_to_st:.4%}")
            self.buy(self.other_exchange, self.trading_pair_other, self.order_amount, OrderType.LIMIT, other_ask)
            self.sell(self.stellar_exchange, self.trading_pair_stellar, self.order_amount, OrderType.LIMIT, stellar_bid)
            self._total_arb_profits += profit_ot_to_st * self.order_amount

    def format_status(self) -> str:
        return f"\n  Stellar Arb | Profits: {self._total_arb_profits:.4f}"
