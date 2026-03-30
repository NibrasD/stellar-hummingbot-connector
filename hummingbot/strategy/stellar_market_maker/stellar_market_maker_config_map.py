from decimal import Decimal

from hummingbot.client.config.config_validators import (
    validate_decimal, validate_market_trading_pair)
from hummingbot.client.config.config_var import ConfigVar

stellar_market_maker_config_map = {
    "strategy": ConfigVar(key="strategy", prompt="", default="stellar_market_maker"),
    "market": ConfigVar(
        key="market",
        prompt="Enter the trading pair for the exchange (e.g. XLM-USDC) >>> ",
        type_str="str",
        validator=lambda v: validate_market_trading_pair("stellar", v),
        prompt_on_new=True,
    ),
    "bid_spread": ConfigVar(
        key="bid_spread",
        prompt="How far away from the mid price do you want to place the first bid order? (Enter 1 to indicate 1%) >>> ",
        type_str="decimal",
        validator=lambda v: validate_decimal(v, Decimal("0"), inclusive=False),
        prompt_on_new=True,
    ),
    "ask_spread": ConfigVar(
        key="ask_spread",
        prompt="How far away from the mid price do you want to place the first ask order? (Enter 1 to indicate 1%) >>> ",
        type_str="decimal",
        validator=lambda v: validate_decimal(v, Decimal("0"), inclusive=False),
        prompt_on_new=True,
    ),
    "order_amount": ConfigVar(
        key="order_amount",
        prompt="What is the amount of base asset per order? >>> ",
        type_str="decimal",
        validator=lambda v: validate_decimal(v, Decimal("0"), inclusive=False),
        prompt_on_new=True,
    ),
    "min_profitability": ConfigVar(
        key="min_profitability",
        prompt="What is the minimum profitability required before placing orders? (e.g. 0.1 for 0.1%) >>> ",
        type_str="decimal",
        validator=lambda v: validate_decimal(v, Decimal("0"), inclusive=False),
        prompt_on_new=True,
    ),
}
