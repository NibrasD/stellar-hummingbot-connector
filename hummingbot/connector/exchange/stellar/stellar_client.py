# hummingbot/connector/exchange/stellar/stellar_client.py
"""
Stellar network client — exclusively uses Soroban RPC for all interactions.
Provides methods for transaction submission, account queries, orderbook data,
and event streaming via the Soroban RPC JSON-RPC 2.0 API.
"""

import asyncio
import logging
from decimal import Decimal
from typing import Any, Dict, List, Optional

from stellar_sdk import Asset

from .stellar_constants import (
    HORIZON_URL_MAINNET,
    HORIZON_URL_TESTNET,
    RPC_GET_EVENTS,
    RPC_GET_LATEST_LEDGER,
    RPC_GET_LEDGER_ENTRIES,
    RPC_GET_NETWORK,
    RPC_GET_TRANSACTION,
    RPC_SEND_TRANSACTION,
    SOROBAN_RPC_URL_MAINNET,
    TRANSACTION_MAX_RETRIES,
    TRANSACTION_POLL_INTERVAL,
)
from .stellar_web_utils import horizon_request, rpc_request
from .stellar_xdr_utils import (
    build_account_ledger_key,
    build_offer_ledger_key,
    build_trustline_ledger_key,
    parse_account_entry,
    parse_offer_entry,
    parse_trustline_entry,
)

logger = logging.getLogger(__name__)


class StellarClient:
    """
    Client for interacting with the Stellar network via Soroban RPC.
    Supports multiple RPC endpoints with automatic failover.
    Uses Horizon only as a fallback for DEX orderbook queries (which Soroban RPC
    does not natively support via a single call).
    """

    # Default fallback RPC endpoints per network
    _FALLBACK_RPC_URLS = {
        "PUBLIC": [
            "https://soroban-rpc.mainnet.stellar.gateway.fm",
            "https://mainnet.sorobanrpc.com",
            "https://rpc.ankr.com/stellar_soroban",
        ],
        "TESTNET": [
            "https://soroban-testnet.stellar.org",
        ],
    }

    def __init__(self, rpc_url: str = SOROBAN_RPC_URL_MAINNET, network: str = "PUBLIC"):
        self._primary_rpc_url = rpc_url
        self.rpc_url = rpc_url
        self.network = network
        self.horizon_url = HORIZON_URL_MAINNET if network == "PUBLIC" else HORIZON_URL_TESTNET
        self._latest_ledger: int = 0
        self._connected: bool = False

        # Build ordered list of RPC endpoints (primary first, then fallbacks)
        fallbacks = self._FALLBACK_RPC_URLS.get(network, [])
        self._rpc_endpoints = [rpc_url]
        for fb in fallbacks:
            if fb != rpc_url:
                self._rpc_endpoints.append(fb)
        self._current_rpc_index = 0

    # ──────────────────────────────────────────
    # Connection & Health
    # ──────────────────────────────────────────

    async def check_connection(self) -> bool:
        """
        Verifies connectivity to Soroban RPC endpoints.
        Tries each endpoint in order until one succeeds (failover).
        """
        for i, endpoint in enumerate(self._rpc_endpoints):
            try:
                result = await rpc_request(endpoint, RPC_GET_NETWORK)
                self.rpc_url = endpoint
                self._current_rpc_index = i
                self._connected = True
                if endpoint != self._primary_rpc_url:
                    logger.warning(f"Primary RPC unavailable, failed over to: {endpoint}")
                logger.info(f"Connected to Stellar RPC: {result.get('passphrase', 'unknown network')}")
                return True
            except Exception as e:
                logger.warning(f"RPC endpoint {endpoint} unreachable: {e}")
                continue

        self._connected = False
        logger.error(f"All {len(self._rpc_endpoints)} RPC endpoints failed. No connection.")
        return False

    @property
    def is_connected(self) -> bool:
        return self._connected

    @property
    def active_rpc_url(self) -> str:
        """Returns the currently active RPC endpoint."""
        return self.rpc_url

    @property
    def rpc_endpoint_count(self) -> int:
        """Returns the total number of configured RPC endpoints."""
        return len(self._rpc_endpoints)

    async def get_latest_ledger(self) -> Dict[str, Any]:
        """
        Gets the latest ledger information from Soroban RPC.
        """
        result = await rpc_request(self.rpc_url, RPC_GET_LATEST_LEDGER)
        self._latest_ledger = result.get("sequence", 0)
        return result

    # ──────────────────────────────────────────
    # Transaction Submission
    # ──────────────────────────────────────────

    async def submit_transaction(self, xdr_tx: str) -> Dict[str, Any]:
        """
        Submits a signed transaction envelope to Soroban RPC.

        Returns the response which includes 'status' and 'hash'.
        """
        result = await rpc_request(
            self.rpc_url,
            RPC_SEND_TRANSACTION,
            {"transaction": xdr_tx},
        )
        logger.info(f"Transaction submitted: hash={result.get('hash', 'N/A')}, " f"status={result.get('status', 'unknown')}")
        return result

    async def get_transaction_status(self, tx_hash: str) -> Dict[str, Any]:
        """
        Gets the status of a submitted transaction by hash.
        """
        return await rpc_request(
            self.rpc_url,
            RPC_GET_TRANSACTION,
            {"hash": tx_hash},
        )

    async def submit_and_wait(
        self,
        xdr_tx: str,
        max_retries: int = TRANSACTION_MAX_RETRIES,
        poll_interval: float = TRANSACTION_POLL_INTERVAL,
    ) -> Dict[str, Any]:
        """
        Submits a transaction and waits for confirmation.

        Returns the final transaction result including resultXdr.
        """
        submit_result = await self.submit_transaction(xdr_tx)
        status = submit_result.get("status", "")

        if status == "ERROR":
            return {
                "status": "FAILED",
                "error": submit_result.get("errorResultXdr", "Unknown submission error"),
                "hash": submit_result.get("hash"),
            }

        tx_hash = submit_result.get("hash")
        if not tx_hash:
            return {"status": "FAILED", "error": "No transaction hash returned"}

        # Poll for completion
        for attempt in range(max_retries):
            await asyncio.sleep(poll_interval)

            try:
                status_result = await self.get_transaction_status(tx_hash)
                tx_status = status_result.get("status", "")

                if tx_status == "SUCCESS":
                    return {
                        "status": "SUCCESS",
                        "hash": tx_hash,
                        "resultXdr": status_result.get("resultXdr", ""),
                        "ledger": status_result.get("ledger"),
                        "envelopeXdr": status_result.get("envelopeXdr", ""),
                    }
                elif tx_status == "FAILED":
                    return {
                        "status": "FAILED",
                        "hash": tx_hash,
                        "resultXdr": status_result.get("resultXdr", ""),
                        "error": "Transaction failed on-chain",
                    }
                elif tx_status == "NOT_FOUND":
                    # Still pending
                    continue
                else:
                    logger.debug(f"Tx {tx_hash[:12]}... status: {tx_status} (attempt {attempt + 1})")

            except Exception as e:
                logger.warning(f"Error polling tx status (attempt {attempt + 1}): {e}")

        return {
            "status": "TIMEOUT",
            "hash": tx_hash,
            "error": f"Transaction not confirmed after {max_retries} attempts",
        }

    # ──────────────────────────────────────────
    # Account Queries (via RPC getLedgerEntries)
    # ──────────────────────────────────────────

    async def get_account(self, account_id: str) -> Dict[str, Any]:
        """
        Gets account details using Soroban RPC getLedgerEntries.
        Returns native balance, sequence number.
        """
        key_xdr = build_account_ledger_key(account_id)
        result = await rpc_request(
            self.rpc_url,
            RPC_GET_LEDGER_ENTRIES,
            {"keys": [key_xdr]},
        )

        entries = result.get("entries", [])
        if not entries:
            raise AccountNotFoundError(f"Account {account_id} not found on ledger")

        parsed = parse_account_entry(entries[0]["xdr"])
        if not parsed:
            raise ValueError(f"Could not parse account entry for {account_id}")

        return parsed

    async def get_account_sequence(self, account_id: str) -> int:
        """
        Gets just the sequence number for an account.
        """
        account = await self.get_account(account_id)
        return account["sequence"]

    async def get_balances(self, account_id: str, assets: List[Asset] = None) -> Dict[str, Decimal]:
        """
        Gets all balances for an account using Soroban RPC getLedgerEntries.
        Fetches native balance + trustline balances.
        """
        balances = {}

        # 1. Get native XLM balance from account entry
        account = await self.get_account(account_id)
        balances["XLM"] = account["balance"]

        # 2. Get trustline balances
        if assets:
            non_native_assets = [a for a in assets if not a.is_native()]
            if non_native_assets:
                keys = [build_trustline_ledger_key(account_id, asset) for asset in non_native_assets]

                try:
                    result = await rpc_request(
                        self.rpc_url,
                        RPC_GET_LEDGER_ENTRIES,
                        {"keys": keys},
                    )

                    for entry_data in result.get("entries", []):
                        parsed = parse_trustline_entry(entry_data["xdr"])
                        if parsed:
                            asset_key = parsed["asset"]["code"]
                            balances[asset_key] = parsed["balance"]
                except Exception as e:
                    logger.warning(f"Failed to fetch trustline balances via RPC: {e}")
        else:
            # Fallback: fetch all trustlines via Horizon when specific assets unknown
            try:
                data = await horizon_request(
                    self.horizon_url,
                    f"/accounts/{account_id}",
                )
                for bal in data.get("balances", []):
                    if bal.get("asset_type") != "native":
                        balances[bal["asset_code"]] = Decimal(bal["balance"])
            except Exception as e:
                logger.warning(f"Failed to fetch trustline balances via Horizon: {e}")

        return balances

    # ──────────────────────────────────────────
    # Offer Queries (via RPC getLedgerEntries)
    # ──────────────────────────────────────────

    async def get_offer(self, seller_id: str, offer_id: int) -> Optional[Dict[str, Any]]:
        """
        Gets a specific offer by seller ID and offer ID using Soroban RPC.
        """
        key_xdr = build_offer_ledger_key(seller_id, offer_id)
        try:
            result = await rpc_request(
                self.rpc_url,
                RPC_GET_LEDGER_ENTRIES,
                {"keys": [key_xdr]},
            )
            entries = result.get("entries", [])
            if entries:
                return parse_offer_entry(entries[0]["xdr"])
            return None  # Offer not found (filled or cancelled)
        except Exception as e:
            logger.error(f"Failed to fetch offer {offer_id}: {e}")
            return None

    async def get_offers_for_account(self, account_id: str, offer_ids: List[int]) -> List[Dict[str, Any]]:
        """
        Gets multiple offers for an account in a single RPC call.
        """
        if not offer_ids:
            return []

        keys = [build_offer_ledger_key(account_id, oid) for oid in offer_ids]
        try:
            result = await rpc_request(
                self.rpc_url,
                RPC_GET_LEDGER_ENTRIES,
                {"keys": keys},
            )
            offers = []
            for entry_data in result.get("entries", []):
                parsed = parse_offer_entry(entry_data["xdr"])
                if parsed:
                    offers.append(parsed)
            return offers
        except Exception as e:
            logger.error(f"Failed to fetch offers for {account_id}: {e}")
            return []

    # ──────────────────────────────────────────
    # Order Book (Horizon fallback — RPC doesn't have a DEX orderbook method)
    # ──────────────────────────────────────────

    async def get_order_book(
        self,
        selling_asset: Asset,
        buying_asset: Asset,
        limit: int = 50,
    ) -> Dict[str, List]:
        """
        Fetches the DEX orderbook via Horizon.
        Note: Soroban RPC does not have a native orderbook query method.
        This is the one area where Horizon is required as a data source.
        """
        params = {"limit": str(limit)}

        if selling_asset.is_native():
            params["selling_asset_type"] = "native"
        else:
            params["selling_asset_type"] = "credit_alphanum4" if len(selling_asset.code) <= 4 else "credit_alphanum12"
            params["selling_asset_code"] = selling_asset.code
            params["selling_asset_issuer"] = selling_asset.issuer

        if buying_asset.is_native():
            params["buying_asset_type"] = "native"
        else:
            params["buying_asset_type"] = "credit_alphanum4" if len(buying_asset.code) <= 4 else "credit_alphanum12"
            params["buying_asset_code"] = buying_asset.code
            params["buying_asset_issuer"] = buying_asset.issuer

        data = await horizon_request(self.horizon_url, "/order_book", params)

        return {
            "bids": [[float(bid["price"]), float(bid["amount"])] for bid in data.get("bids", [])],
            "asks": [[float(ask["price"]), float(ask["amount"])] for ask in data.get("asks", [])],
        }

    # ──────────────────────────────────────────
    # Trade Queries (Horizon — RPC getEvents alternative)
    # ──────────────────────────────────────────

    async def get_trades(
        self,
        base_asset: Asset,
        counter_asset: Asset,
        cursor: str = None,
        limit: int = 50,
        order: str = "desc",
    ) -> List[Dict[str, Any]]:
        """
        Fetches recent trades for a trading pair via Horizon.
        """
        params = {"limit": str(limit), "order": order}

        if base_asset.is_native():
            params["base_asset_type"] = "native"
        else:
            params["base_asset_type"] = "credit_alphanum4" if len(base_asset.code) <= 4 else "credit_alphanum12"
            params["base_asset_code"] = base_asset.code
            params["base_asset_issuer"] = base_asset.issuer

        if counter_asset.is_native():
            params["counter_asset_type"] = "native"
        else:
            params["counter_asset_type"] = "credit_alphanum4" if len(counter_asset.code) <= 4 else "credit_alphanum12"
            params["counter_asset_code"] = counter_asset.code
            params["counter_asset_issuer"] = counter_asset.issuer

        if cursor:
            params["cursor"] = cursor

        data = await horizon_request(self.horizon_url, "/trades", params)
        return data.get("_embedded", {}).get("records", [])

    # ──────────────────────────────────────────
    # Events (via Soroban RPC — for Soroban AMMs)
    # ──────────────────────────────────────────

    async def get_events(
        self,
        start_ledger: int = None,
        event_type: str = "contract",
        contract_ids: List[str] = None,
        topics: List[List[str]] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """
        Fetches events from Soroban RPC. Used for monitoring smart contract events
        (e.g., Soroban AMM swaps on Soroswap/Aquarius contracts).
        """
        params = {"pagination": {"limit": limit}}

        if start_ledger:
            params["startLedger"] = start_ledger
        if event_type:
            params["filters"] = [{"type": event_type}]
            if contract_ids:
                params["filters"][0]["contractIds"] = contract_ids
            if topics:
                params["filters"][0]["topics"] = topics

        result = await rpc_request(self.rpc_url, RPC_GET_EVENTS, params)
        return result.get("events", [])

    # ──────────────────────────────────────────
    # Soroban Contract Invocation (for AMM support)
    # ──────────────────────────────────────────

    async def simulate_transaction(self, xdr_tx: str) -> Dict[str, Any]:
        """
        Simulates a transaction to get resource footprint and fees.
        Used for Soroban smart contract interactions (AMMs).
        """
        return await rpc_request(
            self.rpc_url,
            "simulateTransaction",
            {"transaction": xdr_tx},
        )


class AccountNotFoundError(Exception):
    """Raised when an account is not found on the Stellar ledger."""
