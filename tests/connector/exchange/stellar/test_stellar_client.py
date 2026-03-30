# tests/connector/exchange/stellar/test_stellar_client.py
"""Unit tests for StellarClient — RPC and Horizon network communication."""

import unittest
from unittest.mock import patch

from hummingbot.connector.exchange.stellar.stellar_client import (
    AccountNotFoundError,
    StellarClient,
)


class TestStellarClient(unittest.IsolatedAsyncioTestCase):
    """Tests for StellarClient network operations."""

    def setUp(self):
        self.client = StellarClient(
            rpc_url="https://soroban-testnet.stellar.org",
            network="TESTNET",
        )

    def test_init(self):
        """Test client initialization."""
        self.assertEqual(self.client.rpc_url, "https://soroban-testnet.stellar.org")
        self.assertEqual(self.client.network, "TESTNET")
        self.assertFalse(self.client.is_connected)

    @patch("hummingbot.connector.exchange.stellar.stellar_web_utils.rpc_request")
    async def test_check_connection_success(self, mock_rpc):
        """Test successful connection check."""
        mock_rpc.return_value = {"passphrase": "Test SDF Network"}
        result = await self.client.check_connection()
        self.assertTrue(result)
        self.assertTrue(self.client.is_connected)

    @patch("hummingbot.connector.exchange.stellar.stellar_web_utils.rpc_request")
    async def test_check_connection_failure(self, mock_rpc):
        """Test failed connection check."""
        mock_rpc.side_effect = Exception("Connection refused")
        result = await self.client.check_connection()
        self.assertFalse(result)
        self.assertFalse(self.client.is_connected)

    @patch("hummingbot.connector.exchange.stellar.stellar_web_utils.rpc_request")
    async def test_submit_transaction(self, mock_rpc):
        """Test transaction submission."""
        mock_rpc.return_value = {"status": "PENDING", "hash": "abc123"}
        result = await self.client.submit_transaction("fake_xdr")
        self.assertEqual(result["status"], "PENDING")
        self.assertEqual(result["hash"], "abc123")

    @patch("hummingbot.connector.exchange.stellar.stellar_web_utils.rpc_request")
    async def test_get_transaction_status(self, mock_rpc):
        """Test transaction status query."""
        mock_rpc.return_value = {"status": "SUCCESS", "resultXdr": "AAAA"}
        result = await self.client.get_transaction_status("abc123")
        self.assertEqual(result["status"], "SUCCESS")

    @patch("hummingbot.connector.exchange.stellar.stellar_web_utils.rpc_request")
    async def test_submit_and_wait_success(self, mock_rpc):
        """Test submit and wait for success."""
        mock_rpc.side_effect = [
            {"status": "PENDING", "hash": "tx_hash_1"},  # submit
            {"status": "SUCCESS", "resultXdr": "XXXX", "ledger": 12345},  # poll
        ]
        result = await self.client.submit_and_wait("fake_xdr", max_retries=2, poll_interval=0.1)
        self.assertEqual(result["status"], "SUCCESS")
        self.assertEqual(result["hash"], "tx_hash_1")

    @patch("hummingbot.connector.exchange.stellar.stellar_web_utils.rpc_request")
    async def test_submit_and_wait_timeout(self, mock_rpc):
        """Test submit and wait timeout."""
        mock_rpc.side_effect = [
            {"status": "PENDING", "hash": "tx_hash_2"},
            {"status": "NOT_FOUND"},
            {"status": "NOT_FOUND"},
        ]
        result = await self.client.submit_and_wait("fake_xdr", max_retries=2, poll_interval=0.1)
        self.assertEqual(result["status"], "TIMEOUT")

    @patch("hummingbot.connector.exchange.stellar.stellar_web_utils.rpc_request")
    async def test_get_account_not_found(self, mock_rpc):
        """Test account not found error."""
        mock_rpc.return_value = {"entries": []}
        with self.assertRaises(AccountNotFoundError):
            await self.client.get_account("GABC123")

    @patch("hummingbot.connector.exchange.stellar.stellar_web_utils.rpc_request")
    async def test_get_latest_ledger(self, mock_rpc):
        """Test fetching latest ledger."""
        mock_rpc.return_value = {"sequence": 54321}
        result = await self.client.get_latest_ledger()
        self.assertEqual(result["sequence"], 54321)

    @patch("hummingbot.connector.exchange.stellar.stellar_web_utils.rpc_request")
    async def test_get_offer_not_found(self, mock_rpc):
        """Test getting an offer that doesn't exist."""
        mock_rpc.return_value = {"entries": []}
        result = await self.client.get_offer("GXXX", 999)
        self.assertIsNone(result)

    @patch("hummingbot.connector.exchange.stellar.stellar_web_utils.horizon_request")
    async def test_get_order_book(self, mock_horizon):
        """Test orderbook fetching via Horizon."""
        from stellar_sdk import Asset

        mock_horizon.return_value = {
            "bids": [{"price": "0.1", "amount": "100"}],
            "asks": [{"price": "0.11", "amount": "200"}],
        }
        result = await self.client.get_order_book(Asset.native(), Asset("USDC", "GXXX"))
        self.assertEqual(len(result["bids"]), 1)
        self.assertEqual(len(result["asks"]), 1)
        self.assertEqual(result["bids"][0][0], 0.1)

    @patch("hummingbot.connector.exchange.stellar.stellar_web_utils.horizon_request")
    async def test_get_trades(self, mock_horizon):
        """Test trade history fetching."""
        from stellar_sdk import Asset

        mock_horizon.return_value = {
            "_embedded": {
                "records": [
                    {"id": "t1", "price": {"n": 1, "d": 10}, "base_amount": "50"},
                    {"id": "t2", "price": {"n": 11, "d": 100}, "base_amount": "30"},
                ]
            }
        }
        result = await self.client.get_trades(Asset.native(), Asset("USDC", "GXXX"))
        self.assertEqual(len(result), 2)


if __name__ == "__main__":
    unittest.main()
