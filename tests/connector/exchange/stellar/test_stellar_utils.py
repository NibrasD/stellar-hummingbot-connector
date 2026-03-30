# tests/connector/exchange/stellar/test_stellar_utils.py
"""Unit tests for Stellar utility functions."""

import unittest
from decimal import Decimal

from stellar_sdk import Asset

from hummingbot.connector.exchange.stellar.stellar_utils import (
    format_asset_to_symbol,
    format_trading_pair,
    get_asset_from_symbol,
    get_channel_secrets_list,
    split_trading_pair,
    stroops_to_xlm,
    xlm_to_stroops,
)


class TestStellarUtils(unittest.TestCase):
    """Tests for Stellar utility functions."""

    def test_get_asset_native_xlm(self):
        """Test XLM native asset conversion."""
        asset = get_asset_from_symbol("XLM")
        self.assertTrue(asset.is_native())

    def test_get_asset_native_lowercase(self):
        """Test case insensitivity for native asset."""
        asset = get_asset_from_symbol("xlm")
        self.assertTrue(asset.is_native())

    def test_get_asset_native_keyword(self):
        """Test 'native' keyword."""
        asset = get_asset_from_symbol("native")
        self.assertTrue(asset.is_native())

    def test_get_asset_issued(self):
        """Test issued asset conversion."""
        symbol = "USDC-GA5ZSEJYB37JRC5AVCIA5MOP4RHTM335X2KGX3IHOJAPP5RE34K4KZVN"
        asset = get_asset_from_symbol(symbol)
        self.assertEqual(asset.code, "USDC")
        self.assertEqual(asset.issuer, "GA5ZSEJYB37JRC5AVCIA5MOP4RHTM335X2KGX3IHOJAPP5RE34K4KZVN")

    def test_get_asset_invalid(self):
        """Test invalid asset symbol raises error."""
        with self.assertRaises(ValueError):
            get_asset_from_symbol("INVALID_SYMBOL_FORMAT_HERE")

    def test_format_asset_native(self):
        """Test formatting native asset to symbol."""
        self.assertEqual(format_asset_to_symbol(Asset.native()), "XLM")

    def test_format_asset_issued(self):
        """Test formatting issued asset to symbol."""
        asset = Asset("USDC", "GA5ZSEJYB37JRC5AVCIA5MOP4RHTM335X2KGX3IHOJAPP5RE34K4KZVN")
        result = format_asset_to_symbol(asset)
        self.assertTrue(result.startswith("USDC-GA5Z"))

    def test_format_trading_pair(self):
        """Test trading pair formatting."""
        base = Asset("USDC", "GA5ZSEJYB37JRC5AVCIA5MOP4RHTM335X2KGX3IHOJAPP5RE34K4KZVN")
        quote = Asset.native()
        pair = format_trading_pair(base, quote)
        self.assertIn("USDC", pair)
        self.assertIn("XLM", pair)

    def test_split_trading_pair_simple(self):
        """Test simple trading pair split."""
        base, quote = split_trading_pair("XLM-USDC")
        self.assertEqual(base, "XLM")
        self.assertEqual(quote, "USDC")

    def test_split_trading_pair_with_issuer_base(self):
        """Test split with issued base asset."""
        base, quote = split_trading_pair("USDC-GA5ZSEJYB37-XLM")
        self.assertEqual(base, "USDC-GA5ZSEJYB37")
        self.assertEqual(quote, "XLM")

    def test_split_trading_pair_two_issued(self):
        """Test split with two issued assets."""
        base, quote = split_trading_pair("USDC-GA5Z-EURC-GB3X")
        self.assertEqual(base, "USDC-GA5Z")
        self.assertEqual(quote, "EURC-GB3X")

    def test_stroops_to_xlm(self):
        """Test stroops to XLM conversion."""
        self.assertEqual(stroops_to_xlm(10000000), Decimal("1"))
        self.assertEqual(stroops_to_xlm(1), Decimal("0.0000001"))

    def test_xlm_to_stroops(self):
        """Test XLM to stroops conversion."""
        self.assertEqual(xlm_to_stroops(Decimal("1")), 10000000)
        self.assertEqual(xlm_to_stroops(Decimal("0.0000001")), 1)

    def test_get_channel_secrets_empty(self):
        """Test empty channel secrets."""
        self.assertEqual(get_channel_secrets_list(""), [])
        self.assertEqual(get_channel_secrets_list("  "), [])

    def test_get_channel_secrets_single(self):
        """Test single channel secret."""
        result = get_channel_secrets_list("SECRET1")
        self.assertEqual(result, ["SECRET1"])

    def test_get_channel_secrets_multiple(self):
        """Test multiple channel secrets."""
        result = get_channel_secrets_list("SECRET1, SECRET2, SECRET3")
        self.assertEqual(result, ["SECRET1", "SECRET2", "SECRET3"])


if __name__ == "__main__":
    unittest.main()
