# hummingbot/connector/exchange/stellar/stellar_api_user_stream_data_source.py
"""
User stream data source for the Stellar connector.
Monitors user-specific events: balance changes, order updates, and trade fills.
Uses Soroban RPC getLedgerEntries for real-time state polling.
"""

import asyncio
import logging
import time
from decimal import Decimal
from typing import Any, Dict, List, Optional

from hummingbot.core.data_type.user_stream_tracker_data_source import UserStreamTrackerDataSource
from hummingbot.logger import HummingbotLogger

from .stellar_auth import StellarAuth
from .stellar_client import StellarClient
from .stellar_constants import BALANCE_POLL_INTERVAL, USER_STREAM_POLL_INTERVAL

logger = logging.getLogger(__name__)


class StellarAPIUserStreamDataSource(UserStreamTrackerDataSource):
    """
    Polls the Stellar network for user-specific updates:
    - Balance changes (native XLM + issued assets)
    - Order status changes (offer exists/removed on ledger)
    - Trade fills

    Uses Soroban RPC getLedgerEntries for direct ledger state queries.
    """

    _logger: Optional[HummingbotLogger] = None

    def __init__(
        self,
        auth: StellarAuth,
        client: StellarClient,
        trading_pairs: List[str],
    ):
        super().__init__()
        self._auth = auth
        self._client = client
        self._trading_pairs = trading_pairs
        self._last_balance_poll: float = 0
        self._known_balances: Dict[str, Decimal] = {}
        self._tracked_offer_ids: Dict[int, Dict[str, Any]] = {}  # offer_id -> order info

    @property
    def last_recv_time(self) -> float:
        return self._last_balance_poll

    async def listen_for_user_stream(
        self,
        output: asyncio.Queue,
    ):
        """
        Main loop that listens for user-specific updates.
        Produces messages to the output queue for the exchange connector.
        """
        while True:
            try:
                await self._poll_balances(output)
                await self._poll_order_statuses(output)
                await asyncio.sleep(USER_STREAM_POLL_INTERVAL)

            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.error(f"Error in user stream: {e}", exc_info=True)
                await asyncio.sleep(USER_STREAM_POLL_INTERVAL * 2)

    async def _poll_balances(self, output: asyncio.Queue):
        """
        Polls account balances via Soroban RPC.
        Only sends updates when balances change.
        """
        now = time.time()
        if now - self._last_balance_poll < BALANCE_POLL_INTERVAL:
            return

        self._last_balance_poll = now

        try:
            account_id = self._auth.master_public_key
            balances = await self._client.get_balances(account_id)

            # Detect changes
            changed = False
            for asset, balance in balances.items():
                if asset not in self._known_balances or self._known_balances[asset] != balance:
                    changed = True
                    break

            if changed:
                self._known_balances = balances
                output.put_nowait(
                    {
                        "type": "balance_update",
                        "balances": {k: str(v) for k, v in balances.items()},
                        "timestamp": now,
                    }
                )
                logger.debug(f"Balance update: {dict(balances)}")

        except Exception as e:
            logger.warning(f"Failed to poll balances: {e}")

    async def _poll_order_statuses(self, output: asyncio.Queue):
        """
        Checks if tracked offers still exist on the ledger.
        If an offer disappears, it was either filled or cancelled.
        """
        if not self._tracked_offer_ids:
            return

        account_id = self._auth.master_public_key
        offer_ids = list(self._tracked_offer_ids.keys())

        try:
            existing_offers = await self._client.get_offers_for_account(account_id, offer_ids)
            existing_ids = {o["offer_id"] for o in existing_offers}

            # Check for removed offers
            for offer_id in offer_ids:
                if offer_id not in existing_ids:
                    order_info = self._tracked_offer_ids.pop(offer_id, {})
                    output.put_nowait(
                        {
                            "type": "order_removed",
                            "offer_id": offer_id,
                            "order_info": order_info,
                            "timestamp": time.time(),
                        }
                    )
                    logger.info(f"Offer {offer_id} removed from ledger (filled or cancelled)")

            # Check for amount changes (partial fills)
            for offer in existing_offers:
                offer_id = offer["offer_id"]
                if offer_id in self._tracked_offer_ids:
                    tracked = self._tracked_offer_ids[offer_id]
                    if "amount" in tracked and offer["amount"] != tracked.get("last_amount"):
                        tracked["last_amount"] = offer["amount"]
                        output.put_nowait(
                            {
                                "type": "order_updated",
                                "offer_id": offer_id,
                                "current_amount": str(offer["amount"]),
                                "price": str(offer["price"]),
                                "timestamp": time.time(),
                            }
                        )

        except Exception as e:
            logger.warning(f"Failed to poll order statuses: {e}")

    def track_order(self, offer_id: int, order_info: Dict[str, Any]):
        """Start tracking an offer for status updates."""
        self._tracked_offer_ids[offer_id] = order_info

    def untrack_order(self, offer_id: int):
        """Stop tracking an offer."""
        self._tracked_offer_ids.pop(offer_id, None)

    def get_tracked_orders(self) -> Dict[int, Dict[str, Any]]:
        """Returns all currently tracked orders."""
        return dict(self._tracked_offer_ids)
