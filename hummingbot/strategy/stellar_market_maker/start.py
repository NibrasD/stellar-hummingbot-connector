from decimal import Decimal

from hummingbot.strategy.stellar_market_maker.stellar_market_maker import \
    StellarMarketMaker
from hummingbot.strategy.stellar_market_maker.stellar_market_maker_config_map import \
    stellar_market_maker_config_map


async def start(self):
    try:
        market = stellar_market_maker_config_map.get("market").value
        bid_spread = stellar_market_maker_config_map.get("bid_spread").value / Decimal("100")
        ask_spread = stellar_market_maker_config_map.get("ask_spread").value / Decimal("100")
        order_amount = stellar_market_maker_config_map.get("order_amount").value
        min_profitability = stellar_market_maker_config_map.get("min_profitability").value / Decimal("100")

        exchange = "stellar"

        await self.initialize_markets([(exchange, [market])])
        base_exchange = self.markets[exchange]

        self.strategy = StellarMarketMaker(
            exchange=base_exchange,
            trading_pair=market,
            bid_spread=bid_spread,
            ask_spread=ask_spread,
            order_amount=order_amount,
            min_profitability=min_profitability,
        )
    except Exception as e:
        self.logger().error(f"Error initializing stellar_market_maker strategy: {e}")
