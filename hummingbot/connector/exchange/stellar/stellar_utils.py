# hummingbot/connector/exchange/stellar/stellar_utils.py
"""
Utility functions and Hummingbot configuration model for the Stellar connector.
Provides the KEYS config map that Hummingbot uses for `connect stellar`.
"""

from decimal import Decimal
from typing import List

from hummingbot.client.config.config_data_types import BaseConnectorConfigMap
from hummingbot.core.data_type.trade_fee import TradeFeeSchema
from pydantic import ConfigDict, Field, SecretStr
from stellar_sdk import Asset

from .stellar_constants import KNOWN_ASSET_ISSUERS, NATIVE_ASSET_CODE, SOROBAN_RPC_URL_MAINNET, STROOPS_PER_XLM

# Module-level network state for asset resolution
_current_network: str = "PUBLIC"

# ──────────────────────────────────────────────
# Global Connector Settings for Hummingbot
# ──────────────────────────────────────────────
CENTRALIZED = False
EXAMPLE_PAIR = "XLM-USDC"

# ──────────────────────────────────────────────
# Default Trade Fee Schema for Stellar DEX
# ──────────────────────────────────────────────
DEFAULT_FEES = TradeFeeSchema(
    maker_percent_fee_decimal=Decimal("0"),
    taker_percent_fee_decimal=Decimal("0"),
    buy_percent_fee_deducted_from_returns=False,
)


class StellarConfigMap(BaseConnectorConfigMap):
    """
    Configuration fields shown to the user when running `connect stellar` in Hummingbot.
    """

    connector: str = "stellar"

    stellar_rpc_url: str = Field(
        default=SOROBAN_RPC_URL_MAINNET,
        json_schema_extra={
            "prompt": "Enter your Soroban RPC URL",
            "prompt_on_new": True,
            "is_connect_key": True,
        },
    )

    stellar_master_secret: SecretStr = Field(
        default=...,
        json_schema_extra={
            "prompt": "Enter your Stellar master account secret key",
            "prompt_on_new": True,
            "is_secure": True,
            "is_connect_key": True,
        },
    )

    stellar_channel_secrets: str = Field(
        default="",
        json_schema_extra={
            "prompt": "Enter comma-separated channel account secret keys (for parallel tx)",
            "prompt_on_new": True,
            "is_connect_key": True,
        },
    )

    stellar_network: str = Field(
        default="PUBLIC",
        json_schema_extra={
            "prompt": "Enter the network (PUBLIC or TESTNET)",
            "prompt_on_new": True,
            "is_connect_key": True,
        },
    )

    model_config = ConfigDict(title="stellar")


KEYS = StellarConfigMap.model_construct()


# ──────────────────────────────────────────────
# Asset Conversion Utilities
# ──────────────────────────────────────────────


def set_network(network: str):
    """
    Sets the active Stellar network for asset resolution.
    Called by the exchange connector during initialization.
    """
    global _current_network
    _current_network = network.upper()


def get_asset_from_symbol(symbol: str) -> Asset:
    """
    Converts a Hummingbot-style symbol to a Stellar SDK Asset.

    Formats supported:
    - "XLM" → Asset.native()
    - "USDC-GA5ZSEJYB37JRC5AVCIA5MOP4RHTM335X2KGX3IHOJAPP5RE34K4KZVN" → Asset("USDC", "GA5Z...")
    - "USDC" → Auto-resolved via KNOWN_ASSET_ISSUERS registry
    - "native" → Asset.native()
    """
    if symbol.upper() in (NATIVE_ASSET_CODE, "NATIVE"):
        return Asset.native()

    parts = symbol.split("-")
    if len(parts) == 2:
        code, issuer = parts
        return Asset(code, issuer)

    # Try to resolve from known assets registry
    network_assets = KNOWN_ASSET_ISSUERS.get(_current_network, {})
    if symbol.upper() in network_assets:
        return Asset(symbol.upper(), network_assets[symbol.upper()])
    # Also try the other network as fallback
    for net, assets in KNOWN_ASSET_ISSUERS.items():
        if symbol.upper() in assets:
            return Asset(symbol.upper(), assets[symbol.upper()])

    raise ValueError(
        f"Invalid Stellar asset symbol: '{symbol}'. "
        f"Expected 'XLM' or 'CODE-ISSUER_ADDRESS' format. "
        f"Or add it to KNOWN_ASSET_ISSUERS in stellar_constants.py."
    )


def format_asset_to_symbol(asset: Asset) -> str:
    """
    Converts a Stellar SDK Asset to a Hummingbot symbol string.
    """
    if asset.is_native():
        return NATIVE_ASSET_CODE
    return f"{asset.code}-{asset.issuer}"


def format_trading_pair(base: Asset, quote: Asset) -> str:
    """
    Formats a trading pair string from two Stellar Assets.
    """
    return f"{format_asset_to_symbol(base)}-{format_asset_to_symbol(quote)}"


def split_trading_pair(trading_pair: str):
    """
    Splits a trading pair into base and quote asset symbols.
    Handles multi-segment pairs like 'USDC-GA5Z...-XLM'.

    Returns (base_symbol, quote_symbol).
    """
    # Try to find the split point — the quote asset is either 'XLM' or 'CODE-ISSUER'
    parts = trading_pair.split("-")

    if len(parts) == 2:
        # Simple case: "XLM-USDC" or similar
        return parts[0], parts[1]
    elif len(parts) == 3:
        # One issued asset + one native: "USDC-GA5Z...-XLM" or "XLM-USDC-GA5Z..."
        if parts[2].upper() == NATIVE_ASSET_CODE:
            return f"{parts[0]}-{parts[1]}", parts[2]
        elif parts[0].upper() == NATIVE_ASSET_CODE:
            return parts[0], f"{parts[1]}-{parts[2]}"
        else:
            return parts[0], f"{parts[1]}-{parts[2]}"
    elif len(parts) == 4:
        # Two issued assets: "USDC-GA5Z...-EURC-GB3X..."
        return f"{parts[0]}-{parts[1]}", f"{parts[2]}-{parts[3]}"
    else:
        raise ValueError(f"Cannot parse trading pair: {trading_pair}")


def stroops_to_xlm(stroops: int) -> Decimal:
    """Convert stroops to XLM."""
    return Decimal(stroops) / Decimal(STROOPS_PER_XLM)


def xlm_to_stroops(xlm: Decimal) -> int:
    """Convert XLM to stroops."""
    return int(xlm * Decimal(STROOPS_PER_XLM))


def get_channel_secrets_list(channel_secrets_str: str) -> List[str]:
    """
    Parse comma-separated channel secrets string into a list.
    """
    if not channel_secrets_str or not channel_secrets_str.strip():
        return []
    return [s.strip() for s in channel_secrets_str.split(",") if s.strip()]
