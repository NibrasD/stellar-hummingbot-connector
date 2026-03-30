# tests/connector/exchange/stellar/test_stellar_exchange.py
"""
Comprehensive unit tests for the StellarExchange connector.
"""

import time
import unittest
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

from hummingbot.core.data_type.common import OrderType, TradeType
from hummingbot.core.data_type.in_flight_order import InFlightOrder, OrderState

from hummingbot.connector.exchange.stellar.stellar_exchange import StellarExchange


class TestStellarExchange(unittest.IsolatedAsyncioTestCase):
    """Tests for the main StellarExchange connector class."""

    def setUp(self):
        self.rpc_url = "https://soroban-testnet.stellar.org"
        self.master_secret = "SAXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX"
        self.channel_secrets = "SBXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX"

        self.exchange = StellarExchange(
            client_config_map=MagicMock(),
            stellar_rpc_url=self.rpc_url,
            stellar_master_secret=self.master_secret,
            stellar_channel_secrets=self.channel_secrets,
            stellar_network="TESTNET",
            trading_pairs=["USDC-GA5ZSEJYB37JRC5AVCIA5MOP4RHTM335X2KGX3IHOJAPP5RE34K4KZVN-XLM"],
        )

    def test_name(self):
        """Test connector name."""
        self.assertEqual(self.exchange.name, "stellar")

    def test_supported_order_types(self):
        """Test supported order types."""
        types = self.exchange.supported_order_types()
        self.assertIn(OrderType.LIMIT, types)
        self.assertIn(OrderType.LIMIT_MAKER, types)

    def test_status_dict_initial(self):
        """Test initial status dict."""
        status = self.exchange.status_dict
        self.assertIn("network_connected", status)
        self.assertIn("order_books_initialized", status)
        self.assertIn("account_balance_fetched", status)

    def test_trading_pairs(self):
        """Test trading pairs property."""
        self.assertEqual(len(self.exchange.trading_pairs), 1)

    def test_domain(self):
        """Test domain property."""
        self.assertEqual(self.exchange.domain, "testnet")

    @patch("hummingbot.connector.exchange.stellar.stellar_client.StellarClient.check_connection")
    @patch("hummingbot.connector.exchange.stellar.stellar_client.StellarClient.get_balances")
    async def test_start_network(self, mock_balances, mock_conn):
        """Test starting network connection."""
        mock_conn.return_value = True
        mock_balances.return_value = {"XLM": Decimal("100.0")}

        with patch.object(self.exchange._pipeline, "start", new_callable=AsyncMock):
            await self.exchange.start_network()
            mock_conn.assert_called_once()
            mock_balances.assert_called_once()

    @patch("hummingbot.connector.exchange.stellar.stellar_client.StellarClient.check_connection")
    async def test_check_network_connected(self, mock_conn):
        """Test network check when connected."""
        mock_conn.return_value = True
        from hummingbot.core.network_iterator import NetworkStatus

        status = await self.exchange.check_network()
        self.assertEqual(status, NetworkStatus.CONNECTED)

    @patch("hummingbot.connector.exchange.stellar.stellar_client.StellarClient.check_connection")
    async def test_check_network_disconnected(self, mock_conn):
        """Test network check when disconnected."""
        mock_conn.side_effect = Exception("Connection failed")
        from hummingbot.core.network_iterator import NetworkStatus

        status = await self.exchange.check_network()
        self.assertEqual(status, NetworkStatus.NOT_CONNECTED)

    @patch("hummingbot.connector.exchange.stellar.stellar_client.StellarClient.get_balances")
    async def test_update_balances(self, mock_balances):
        """Test balance update."""
        mock_balances.return_value = {
            "XLM": Decimal("500.123"),
            "USDC": Decimal("1000.50"),
        }
        await self.exchange._update_balances()

        self.assertEqual(self.exchange._get_balance("XLM"), Decimal("500.123"))
        self.assertEqual(self.exchange._get_balance("USDC"), Decimal("1000.50"))
        self.assertEqual(self.exchange._get_balance("BTC"), Decimal("0"))

    def test_get_fee(self):
        """Test fee calculation — Stellar DEX has zero maker/taker fees."""
        fee = self.exchange._get_fee("USDC", "XLM", OrderType.LIMIT, TradeType.BUY, Decimal("10"), Decimal("0.1"))
        self.assertEqual(fee.percent, Decimal(0))

    def test_format_status(self):
        """Test status formatting."""
        status_str = self.exchange.format_status()
        self.assertIn("Stellar DEX", status_str)
        self.assertIn("TESTNET", status_str)

    @patch("hummingbot.connector.exchange.stellar.stellar_client.StellarClient.get_offer")
    async def test_request_order_status_open(self, mock_offer):
        """Test order status request when offer exists."""
        mock_offer.return_value = {"offer_id": 123, "amount": Decimal("10")}

        order = InFlightOrder(
            client_order_id="test_order",
            exchange_order_id="123",
            trading_pair="USDC-XLM",
            order_type=OrderType.LIMIT,
            trade_type=TradeType.BUY,
            amount=Decimal("10"),
            price=Decimal("0.1"),
            creation_timestamp=time.time(),
        )

        update = await self.exchange._request_order_status(order)
        self.assertEqual(update.new_state, OrderState.OPEN)

    @patch("hummingbot.connector.exchange.stellar.stellar_client.StellarClient.get_offer")
    async def test_request_order_status_filled(self, mock_offer):
        """Test order status when offer no longer exists (filled)."""
        mock_offer.return_value = None

        order = InFlightOrder(
            client_order_id="test_order",
            exchange_order_id="123",
            trading_pair="USDC-XLM",
            order_type=OrderType.LIMIT,
            trade_type=TradeType.BUY,
            amount=Decimal("10"),
            price=Decimal("0.1"),
            creation_timestamp=time.time(),
        )

        update = await self.exchange._request_order_status(order)
        self.assertEqual(update.new_state, OrderState.FILLED)


if __name__ == "__main__":
    unittest.main()
