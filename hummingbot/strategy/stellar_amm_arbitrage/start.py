from decimal import Decimal

from hummingbot.strategy.stellar_amm_arbitrage.stellar_amm_arbitrage import \
    StellarAmmArbitrage
from hummingbot.strategy.stellar_amm_arbitrage.stellar_amm_arbitrage_config_map import \
    stellar_amm_arbitrage_config_map


async def start(self):
    try:
        market_1 = stellar_amm_arbitrage_config_map.get("market_1").value
        market_2 = stellar_amm_arbitrage_config_map.get("market_2").value
        min_profitability = stellar_amm_arbitrage_config_map.get("min_profitability").value / Decimal("100")
        order_amount = stellar_amm_arbitrage_config_map.get("order_amount").value

        exchange = "stellar"

        await self.initialize_markets([(exchange, [market_1, market_2])])
        base_exchange = self.markets[exchange]

        self.strategy = StellarAmmArbitrage(
            exchange_1=base_exchange,
            exchange_2=base_exchange,
            trading_pair=market_1,
            min_profitability=min_profitability,
            order_amount=order_amount,
        )
    except Exception as e:
        self.logger().error(f"Error initializing stellar_amm_arbitrage strategy: {e}")
