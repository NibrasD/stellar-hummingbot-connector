# hummingbot/connector/exchange/stellar/stellar_auth.py
"""
Authentication and channel account management for Stellar connector.
Implements the channel accounts pattern for parallel transaction submission.
"""

import asyncio
import logging
from typing import Dict, List

from stellar_sdk import Account, Keypair, TransactionBuilder, TransactionEnvelope

from .stellar_constants import DEFAULT_BASE_FEE, NETWORK_PASSPHRASE_PUBLIC, NETWORK_PASSPHRASE_TESTNET

logger = logging.getLogger(__name__)


class StellarAuth:
    """
    Manages authentication and channel accounts for the Stellar connector.

    Channel accounts allow multiple transactions to be submitted in parallel
    without sequence number collisions. Each transaction uses a different
    channel account as the source, while the master account is the signer.
    """

    def __init__(
        self,
        master_secret: str,
        channel_secrets: List[str],
        network: str = "PUBLIC",
    ):
        self.master_keypair = Keypair.from_secret(master_secret)
        self.channel_keypairs = [Keypair.from_secret(s) for s in channel_secrets] if channel_secrets else []
        self.network = network
        self.network_passphrase = NETWORK_PASSPHRASE_PUBLIC if network == "PUBLIC" else NETWORK_PASSPHRASE_TESTNET

        # Channel account concurrency management
        self._channel_semaphores: Dict[str, asyncio.Semaphore] = {kp.public_key: asyncio.Semaphore(1) for kp in self.channel_keypairs}
        self._channel_sequences: Dict[str, int] = {kp.public_key: 0 for kp in self.channel_keypairs}
        self._sequence_lock = asyncio.Lock()

        # If no channel accounts provided, use master as the only "channel"
        if not self.channel_keypairs:
            self._channel_semaphores[self.master_keypair.public_key] = asyncio.Semaphore(1)
            self._channel_sequences[self.master_keypair.public_key] = 0
            logger.warning(
                "No channel accounts configured. Using master account for all transactions. " "This limits concurrency to 1 transaction at a time."
            )

    @property
    def master_public_key(self) -> str:
        return self.master_keypair.public_key

    @property
    def num_channels(self) -> int:
        return max(len(self.channel_keypairs), 1)

    async def acquire_channel(self) -> Keypair:
        """
        Acquires an available channel account for transaction submission.
        Blocks until one becomes available.

        Returns:
            A Keypair for the acquired channel account.
        """
        while True:
            # Try channel accounts first
            for kp in self.channel_keypairs:
                sem = self._channel_semaphores[kp.public_key]
                if not sem.locked():
                    await sem.acquire()
                    logger.debug(f"Acquired channel account: {kp.public_key[:8]}...")
                    return kp

            # Fallback to master if no channels configured
            if not self.channel_keypairs:
                sem = self._channel_semaphores[self.master_keypair.public_key]
                await sem.acquire()
                return self.master_keypair

            # All channels busy, wait and retry
            await asyncio.sleep(0.05)

    def release_channel(self, kp: Keypair):
        """
        Releases a channel account back to the pool.
        """
        pub_key = kp.public_key
        if pub_key in self._channel_semaphores:
            sem = self._channel_semaphores[pub_key]
            if sem.locked():
                sem.release()
                logger.debug(f"Released channel account: {pub_key[:8]}...")

    async def get_sequence_number(self, kp: Keypair, client) -> int:
        """
        Gets the next sequence number for a channel account.
        Fetches from the network on first call, then increments locally.
        Handles sequence conflicts by re-fetching.
        """
        async with self._sequence_lock:
            pub_key = kp.public_key
            if self._channel_sequences[pub_key] == 0:
                account_info = await client.get_account_sequence(pub_key)
                self._channel_sequences[pub_key] = account_info

            self._channel_sequences[pub_key] += 1
            return self._channel_sequences[pub_key]

    async def refresh_sequence_number(self, kp: Keypair, client):
        """
        Forces a refresh of the sequence number from the network.
        Called after a sequence conflict error.
        """
        async with self._sequence_lock:
            pub_key = kp.public_key
            account_info = await client.get_account_sequence(pub_key)
            self._channel_sequences[pub_key] = account_info
            logger.info(f"Refreshed sequence for {pub_key[:8]}... to {account_info}")

    def build_transaction(
        self,
        channel_kp: Keypair,
        sequence: int,
        operations: list,
        base_fee: int = DEFAULT_BASE_FEE,
        timeout: int = 30,
        memo=None,
    ) -> TransactionBuilder:
        """
        Builds a transaction using the channel account as the source,
        with the master account's operations.
        """
        source_account = Account(
            account=channel_kp.public_key,
            sequence=sequence - 1,  # TransactionBuilder auto-increments
        )

        tx_builder = TransactionBuilder(
            source_account=source_account,
            network_passphrase=self.network_passphrase,
            base_fee=base_fee,
        )

        from stellar_sdk import MuxedAccount

        for op in operations:
            # Set the master account as the operation source
            # so channel account only provides the sequence number
            if hasattr(op, "source") and op.source is None:
                op.source = MuxedAccount(self.master_keypair.public_key)
            tx_builder.append_operation(op)

        if memo:
            tx_builder.add_text_memo(memo)

        tx_builder.set_timeout(timeout)
        return tx_builder

    def sign_transaction(self, tx_builder: TransactionBuilder, channel_kp: Keypair) -> str:
        """
        Signs a transaction with both the master key and the channel key.
        Returns the base64-encoded XDR transaction envelope.
        """
        tx = tx_builder.build()

        # Sign with master (authorizes operations)
        tx.sign(self.master_keypair)

        # Sign with channel (authorizes source account / sequence)
        if channel_kp.public_key != self.master_keypair.public_key:
            tx.sign(channel_kp)

        return tx.to_xdr()

    def sign_and_return_envelope(self, tx_builder: TransactionBuilder, channel_kp: Keypair) -> TransactionEnvelope:
        """
        Signs and returns the TransactionEnvelope object (not XDR string).
        Useful for inspection before submission.
        """
        tx = tx_builder.build()
        tx.sign(self.master_keypair)
        if channel_kp.public_key != self.master_keypair.public_key:
            tx.sign(channel_kp)
        return tx

    def verify_configured(self) -> bool:
        """
        Verifies that the auth configuration is valid.
        """
        try:
            # Verify master key is valid
            _ = self.master_keypair.public_key

            # Verify channel keys are valid
            for kp in self.channel_keypairs:
                _ = kp.public_key

            return True
        except Exception as e:
            logger.error(f"Auth configuration is invalid: {e}")
            return False
