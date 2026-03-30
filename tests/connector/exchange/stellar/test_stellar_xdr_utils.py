# tests/connector/exchange/stellar/test_stellar_xdr_utils.py
"""Unit tests for XDR utilities."""

import unittest

from stellar_sdk import Asset

from hummingbot.connector.exchange.stellar.stellar_xdr_utils import (
    build_account_ledger_key,
    build_cancel_offer_op,
    build_manage_buy_offer_op,
    build_manage_sell_offer_op,
    decode_transaction_result,
)


class TestStellarXDRUtils(unittest.TestCase):
    """Tests for XDR construction and parsing."""

    def test_build_manage_sell_offer_new(self):
        """Test building a new sell offer."""
        op = build_manage_sell_offer_op(
            selling=Asset.native(),
            buying=Asset("USDC", "GA5ZSEJYB37JRC5AVCIA5MOP4RHTM335X2KGX3IHOJAPP5RE34K4KZVN"),
            amount="100",
            price="0.1",
        )
        self.assertIsNotNone(op)

    def test_build_manage_buy_offer_new(self):
        """Test building a new buy offer."""
        op = build_manage_buy_offer_op(
            selling=Asset("USDC", "GA5ZSEJYB37JRC5AVCIA5MOP4RHTM335X2KGX3IHOJAPP5RE34K4KZVN"),
            buying=Asset.native(),
            amount="50",
            price="10",
        )
        self.assertIsNotNone(op)

    def test_build_cancel_offer(self):
        """Test building a cancel offer operation."""
        op = build_cancel_offer_op(
            selling=Asset.native(),
            buying=Asset("USDC", "GA5ZSEJYB37JRC5AVCIA5MOP4RHTM335X2KGX3IHOJAPP5RE34K4KZVN"),
            offer_id=12345,
        )
        self.assertIsNotNone(op)

    def test_build_account_ledger_key(self):
        """Test building a ledger key for account lookup."""
        key = build_account_ledger_key("GAAZI4TCR3TY5OJHCTJC2A4QSY6CJWJH5IAJTGKIN2ER7LBNVKOCCWN7")
        self.assertIsInstance(key, str)
        self.assertTrue(len(key) > 0)

    def test_decode_transaction_result_invalid_xdr(self):
        """Test decoding invalid XDR returns error gracefully."""
        result = decode_transaction_result("invalid_base64!")
        self.assertFalse(result.get("success", True))
        self.assertIn("error", result)

    def test_build_manage_sell_offer_with_source(self):
        """Test building offer with source account."""
        op = build_manage_sell_offer_op(
            selling=Asset.native(),
            buying=Asset("USDC", "GA5ZSEJYB37JRC5AVCIA5MOP4RHTM335X2KGX3IHOJAPP5RE34K4KZVN"),
            amount="10",
            price="0.5",
            source="GAAZI4TCR3TY5OJHCTJC2A4QSY6CJWJH5IAJTGKIN2ER7LBNVKOCCWN7",
        )
        self.assertIsNotNone(op)

    def test_build_cancel_offer_amount_zero(self):
        """Test cancel offer always uses amount=0."""
        op = build_cancel_offer_op(
            selling=Asset.native(),
            buying=Asset("USDC", "GA5ZSEJYB37JRC5AVCIA5MOP4RHTM335X2KGX3IHOJAPP5RE34K4KZVN"),
            offer_id=999,
        )
        self.assertEqual(op.amount, "0")


if __name__ == "__main__":
    unittest.main()
