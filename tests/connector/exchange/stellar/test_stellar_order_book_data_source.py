# tests/connector/exchange/stellar/test_stellar_order_book_data_source.py
"""Unit tests for StellarAPIOrderBookDataSource."""

import unittest
from unittest.mock import AsyncMock, MagicMock

from hummingbot.connector.exchange.stellar.stellar_api_order_book_data_source import (
    StellarAPIOrderBookDataSource,
)
from hummingbot.connector.exchange.stellar.stellar_client import StellarClient


class TestStellarOrderBookDataSource(unittest.IsolatedAsyncioTestCase):
    """Tests for order book data source."""

    def setUp(self):
        self.client = MagicMock(spec=StellarClient)
        self.trading_pairs = ["XLM-USDC"]
        self.data_source = StellarAPIOrderBookDataSource(
            trading_pairs=self.trading_pairs,
            client=self.client,
        )

    async def test_get_snapshot(self):
        """Test snapshot retrieval."""
        self.client.get_order_book = AsyncMock(
            return_value={
                "bids": [[0.1, 100], [0.09, 200]],
                "asks": [[0.11, 150], [0.12, 300]],
            }
        )

        snapshot = await self.data_source.get_snapshot("XLM-USDC")
        self.assertIn("bids", snapshot)
        self.assertIn("asks", snapshot)
        self.assertEqual(len(snapshot["bids"]), 2)
        self.assertEqual(len(snapshot["asks"]), 2)

    async def test_get_last_traded_prices(self):
        """Test last traded price retrieval."""
        mock_client = MagicMock(spec=StellarClient)
        mock_client.get_trades = AsyncMock(return_value=[{"price": {"n": 11, "d": 100}, "base_amount": "50"}])

        prices = await StellarAPIOrderBookDataSource.get_last_traded_prices(["XLM-USDC"], mock_client)
        self.assertIn("XLM-USDC", prices)
        self.assertAlmostEqual(prices["XLM-USDC"], 0.11, places=2)

    async def test_get_last_traded_prices_empty(self):
        """Test last traded price when no trades exist."""
        mock_client = MagicMock(spec=StellarClient)
        mock_client.get_trades = AsyncMock(return_value=[])

        prices = await StellarAPIOrderBookDataSource.get_last_traded_prices(["XLM-USDC"], mock_client)
        self.assertEqual(prices["XLM-USDC"], 0.0)


if __name__ == "__main__":
    unittest.main()
