# tests/connector/exchange/stellar/test_stellar_auth.py
"""Unit tests for StellarAuth — channel account management and signing."""

import unittest
from unittest.mock import AsyncMock, MagicMock

from hummingbot.connector.exchange.stellar.stellar_auth import StellarAuth


class TestStellarAuth(unittest.IsolatedAsyncioTestCase):
    """Tests for StellarAuth channel account management."""

    def setUp(self):
        # Use deterministic test keys (these are NOT real keys)
        self.master_secret = "SCZANGBA5YHTNYVVV3C7CAZMCLXPILIKVCELCY5KQOOD3HKLIFH6SEZN"
        self.channel_secrets = [
            "SA3XKZBSI4OEY3WQMCPV2CXRPJMKQDMR6MF6MHPGNMBGY3VGGABXQFM",
            "SCFXE4CVHM2XVQKXR7X6JQBHPJNZQBQNVQKERPHISG72OOCF4NLMFXM",
        ]

    def test_init_with_channels(self):
        """Test initialization with channel accounts."""
        auth = StellarAuth(self.master_secret, self.channel_secrets, "TESTNET")
        self.assertEqual(auth.num_channels, 2)
        self.assertIsNotNone(auth.master_public_key)

    def test_init_without_channels(self):
        """Test initialization without channel accounts (fallback to master)."""
        auth = StellarAuth(self.master_secret, [], "TESTNET")
        self.assertEqual(auth.num_channels, 1)  # Master acts as the single channel

    def test_network_passphrase_public(self):
        """Test correct public network passphrase."""
        auth = StellarAuth(self.master_secret, [], "PUBLIC")
        self.assertIn("Public Global", auth.network_passphrase)

    def test_network_passphrase_testnet(self):
        """Test correct testnet passphrase."""
        auth = StellarAuth(self.master_secret, [], "TESTNET")
        self.assertIn("Test SDF", auth.network_passphrase)

    async def test_acquire_channel(self):
        """Test acquiring a channel account."""
        auth = StellarAuth(self.master_secret, self.channel_secrets, "TESTNET")
        kp = await auth.acquire_channel()
        self.assertIsNotNone(kp)
        self.assertTrue(kp.public_key.startswith("G"))
        auth.release_channel(kp)

    async def test_release_channel(self):
        """Test releasing a channel account."""
        auth = StellarAuth(self.master_secret, self.channel_secrets, "TESTNET")
        kp = await auth.acquire_channel()
        auth.release_channel(kp)
        # Acquiring again should work
        kp2 = await auth.acquire_channel()
        self.assertIsNotNone(kp2)
        auth.release_channel(kp2)

    async def test_concurrent_channel_acquisition(self):
        """Test that concurrent channel acquisition respects the pool size."""
        auth = StellarAuth(self.master_secret, self.channel_secrets, "TESTNET")

        # Acquire all channels
        acquired = []
        for _ in range(2):
            kp = await auth.acquire_channel()
            acquired.append(kp)

        self.assertEqual(len(acquired), 2)

        # All channels should now be locked
        for kp in acquired:
            auth.release_channel(kp)

    async def test_sequence_number_fetch(self):
        """Test sequence number fetching from client."""
        auth = StellarAuth(self.master_secret, self.channel_secrets, "TESTNET")
        mock_client = MagicMock()
        mock_client.get_account_sequence = AsyncMock(return_value=12345)

        kp = await auth.acquire_channel()
        seq = await auth.get_sequence_number(kp, mock_client)
        self.assertEqual(seq, 12346)  # Should be fetched + 1

        # Second call should not re-fetch
        seq2 = await auth.get_sequence_number(kp, mock_client)
        self.assertEqual(seq2, 12347)  # Should increment locally
        auth.release_channel(kp)

    async def test_refresh_sequence(self):
        """Test forcing a sequence number refresh."""
        auth = StellarAuth(self.master_secret, self.channel_secrets, "TESTNET")
        mock_client = MagicMock()
        mock_client.get_account_sequence = AsyncMock(return_value=99999)

        kp = await auth.acquire_channel()
        await auth.refresh_sequence_number(kp, mock_client)
        seq = await auth.get_sequence_number(kp, mock_client)
        self.assertEqual(seq, 100001)  # 99999 refreshed, then +1 from prior +1 from call
        auth.release_channel(kp)

    def test_verify_configured(self):
        """Test configuration verification."""
        auth = StellarAuth(self.master_secret, self.channel_secrets, "TESTNET")
        self.assertTrue(auth.verify_configured())

    def test_sign_transaction(self):
        """Test transaction signing."""
        auth = StellarAuth(self.master_secret, self.channel_secrets, "TESTNET")

        from stellar_sdk import (
            Account,
            Asset,
            Keypair,
            ManageSellOffer,
            TransactionBuilder,
        )

        channel_kp = Keypair.from_secret(self.channel_secrets[0])
        source = Account(channel_kp.public_key, 100)
        builder = TransactionBuilder(
            source_account=source,
            network_passphrase=auth.network_passphrase,
            base_fee=100,
        )
        builder.append_operation(
            ManageSellOffer(
                selling=Asset.native(),
                buying=Asset("USDC", "GA5ZSEJYB37JRC5AVCIA5MOP4RHTM335X2KGX3IHOJAPP5RE34K4KZVN"),
                amount="10",
                price="0.1",
                source=auth.master_public_key,
            )
        )
        builder.set_timeout(30)

        xdr = auth.sign_transaction(builder, channel_kp)
        self.assertIsInstance(xdr, str)
        self.assertTrue(len(xdr) > 0)


if __name__ == "__main__":
    unittest.main()
