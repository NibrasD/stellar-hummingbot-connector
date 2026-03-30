from decimal import Decimal

from hummingbot.client.config.config_validators import (
    validate_decimal, validate_market_trading_pair)
from hummingbot.client.config.config_var import ConfigVar

stellar_amm_arbitrage_config_map = {
    "strategy": ConfigVar(key="strategy", prompt="", default="stellar_amm_arbitrage"),
    "market_1": ConfigVar(
        key="market_1",
        prompt="Enter the first trading pair (e.g. XLM-USDC) >>> ",
        type_str="str",
        validator=lambda v: validate_market_trading_pair("stellar", v),
        prompt_on_new=True,
    ),
    "market_2": ConfigVar(
        key="market_2",
        prompt="Enter the second trading pair (e.g. XLM-USDC) >>> ",
        type_str="str",
        validator=lambda v: validate_market_trading_pair("stellar", v),
        prompt_on_new=True,
    ),
    "min_profitability": ConfigVar(
        key="min_profitability",
        prompt="What is the minimum profitability required to execute an arbitrage trade? (e.g. 1.0 for 1%) >>> ",
        type_str="decimal",
        validator=lambda v: validate_decimal(v, Decimal("0"), inclusive=False),
        prompt_on_new=True,
    ),
    "order_amount": ConfigVar(
        key="order_amount",
        prompt="What is the amount of base asset to trade per arbitrage cycle? >>> ",
        type_str="decimal",
        validator=lambda v: validate_decimal(v, Decimal("0"), inclusive=False),
        prompt_on_new=True,
    ),
}
