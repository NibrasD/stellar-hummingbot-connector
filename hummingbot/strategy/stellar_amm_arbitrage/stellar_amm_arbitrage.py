# hummingbot/strategy/stellar_amm_arbitrage/stellar_amm_arbitrage.py
"""
AMM Arbitrage strategy for the Stellar ecosystem.
Supports:
- Intra-Soroban AMM arbitrage (e.g., Soroswap vs Aquarius)
- Classic Stellar AMM vs DEX arbitrage
- Cross-venue arbitrage between Stellar DEX and external CEXs
"""

import asyncio
import logging
from decimal import Decimal
from typing import List

from hummingbot.core.data_type.common import OrderType
from hummingbot.strategy.strategy_py_base import StrategyPyBase

logger = logging.getLogger(__name__)


class StellarAmmArbitrage(StrategyPyBase):
    """
    Arbitrage strategy for the Stellar ecosystem.

    Monitors price differences between:
    1. Stellar DEX orderbook vs Soroban AMMs (Soroswap, Aquarius)
    2. Between different Soroban AMMs
    3. Stellar DEX vs classic liquidity pools

    Executes trades when the price discrepancy exceeds the minimum
    profitability threshold (including network fees).
    """

    def __init__(
        self,
        exchange_1,
        exchange_2,
        trading_pair: str,
        min_profitability: Decimal = Decimal("0.003"),
        order_amount: Decimal = Decimal("10"),
        poll_interval: float = 5.0,
        max_order_age: float = 30.0,
        slippage_buffer: Decimal = Decimal("0.001"),
        network_fee_xlm: Decimal = Decimal("0.00002"),
    ):
        super().__init__()
        self._exchange_1 = exchange_1
        self._exchange_2 = exchange_2
        self._trading_pair = trading_pair
        self._min_profitability = min_profitability
        self._order_amount = order_amount
        self._poll_interval = poll_interval
        self._max_order_age = max_order_age
        self._slippage_buffer = slippage_buffer
        self._network_fee_xlm = network_fee_xlm

        self._last_timestamp: float = 0
        self._total_profit: Decimal = Decimal("0")
        self._total_trades: int = 0
        self._active_arb_orders: List[str] = []

    def tick(self, timestamp: float):
        """Strategy tick — check for arb opportunities."""
        if timestamp - self._last_timestamp < self._poll_interval:
            return
        self._last_timestamp = timestamp

        asyncio.ensure_future(self._check_and_execute_arbitrage())

    async def _check_and_execute_arbitrage(self):
        """Check prices across venues and execute if profitable."""
        try:
            # Fetch order books from both venues
            ob1 = self._exchange_1.get_order_book(self._trading_pair)
            ob2 = self._exchange_2.get_order_book(self._trading_pair)

            if ob1 is None or ob2 is None:
                return

            best_bid_1 = ob1.get_price(True)
            best_ask_1 = ob1.get_price(False)
            best_bid_2 = ob2.get_price(True)
            best_ask_2 = ob2.get_price(False)

            if not all([best_bid_1, best_ask_1, best_bid_2, best_ask_2]):
                return

            best_bid_1 = Decimal(str(best_bid_1))
            best_ask_1 = Decimal(str(best_ask_1))
            best_bid_2 = Decimal(str(best_bid_2))
            best_ask_2 = Decimal(str(best_ask_2))

            # Direction 1: Buy on exchange 1, sell on exchange 2
            profit_1_to_2 = self._calculate_net_profit(
                buy_price=best_ask_1,
                sell_price=best_bid_2,
                amount=self._order_amount,
            )

            if profit_1_to_2 > self._min_profitability:
                adjusted_buy = best_ask_1 * (Decimal("1") + self._slippage_buffer)
                adjusted_sell = best_bid_2 * (Decimal("1") - self._slippage_buffer)

                logger.info(f"🔄 ARB OPPORTUNITY (1→2): " f"Buy@{best_ask_1:.7f} Sell@{best_bid_2:.7f} " f"Net profit: {profit_1_to_2:.4%}")

                buy_id = self._exchange_1.buy(
                    self._trading_pair,
                    self._order_amount,
                    OrderType.LIMIT,
                    adjusted_buy,
                )
                sell_id = self._exchange_2.sell(
                    self._trading_pair,
                    self._order_amount,
                    OrderType.LIMIT,
                    adjusted_sell,
                )

                self._active_arb_orders.extend([buy_id, sell_id])
                self._total_trades += 1
                self._total_profit += profit_1_to_2 * self._order_amount
                return

            # Direction 2: Buy on exchange 2, sell on exchange 1
            profit_2_to_1 = self._calculate_net_profit(
                buy_price=best_ask_2,
                sell_price=best_bid_1,
                amount=self._order_amount,
            )

            if profit_2_to_1 > self._min_profitability:
                adjusted_buy = best_ask_2 * (Decimal("1") + self._slippage_buffer)
                adjusted_sell = best_bid_1 * (Decimal("1") - self._slippage_buffer)

                logger.info(f"🔄 ARB OPPORTUNITY (2→1): " f"Buy@{best_ask_2:.7f} Sell@{best_bid_1:.7f} " f"Net profit: {profit_2_to_1:.4%}")

                buy_id = self._exchange_2.buy(
                    self._trading_pair,
                    self._order_amount,
                    OrderType.LIMIT,
                    adjusted_buy,
                )
                sell_id = self._exchange_1.sell(
                    self._trading_pair,
                    self._order_amount,
                    OrderType.LIMIT,
                    adjusted_sell,
                )

                self._active_arb_orders.extend([buy_id, sell_id])
                self._total_trades += 1
                self._total_profit += profit_2_to_1 * self._order_amount

        except Exception as e:
            logger.error(f"Error in arbitrage check: {e}", exc_info=True)

    def _calculate_net_profit(
        self,
        buy_price: Decimal,
        sell_price: Decimal,
        amount: Decimal,
    ) -> Decimal:
        """
        Calculate net profit percentage after fees.
        Includes network transaction fees for both sides.
        """
        if buy_price <= 0:
            return Decimal("-1")

        gross_profit = (sell_price - buy_price) / buy_price

        # Deduct estimated network fees (2 transactions)
        total_fee_xlm = self._network_fee_xlm * 2
        fee_as_pct = total_fee_xlm / (amount * buy_price) if (amount * buy_price) > 0 else Decimal(0)

        net_profit = gross_profit - fee_as_pct
        return net_profit

    def format_status(self) -> str:
        """Returns strategy status string."""
        lines = []
        lines.append(f"\n  Stellar AMM Arbitrage Status")
        lines.append(f"  ════════════════════════════")
        lines.append(f"  Pair:            {self._trading_pair}")
        lines.append(f"  Min Profit:      {self._min_profitability:.4%}")
        lines.append(f"  Order Amount:    {self._order_amount}")
        lines.append(f"  Poll Interval:   {self._poll_interval}s")
        lines.append(f"  Slippage Buffer: {self._slippage_buffer:.4%}")
        lines.append(f"  ──────────────────────────")
        lines.append(f"  Total Trades:    {self._total_trades}")
        lines.append(f"  Total Profit:    {self._total_profit:.6f}")
        lines.append(f"  Active Orders:   {len(self._active_arb_orders)}")
        return "\n".join(lines)
