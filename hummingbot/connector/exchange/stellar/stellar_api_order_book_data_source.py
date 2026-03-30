# hummingbot/connector/exchange/stellar/stellar_api_order_book_data_source.py
"""
Order book data source for the Stellar DEX connector.
Fetches orderbook snapshots and listens for trades.
Uses Horizon for DEX orderbook data (Soroban RPC lacks native orderbook queries)
and Soroban RPC for event-based trade detection.
"""

import asyncio
import logging
import time
from typing import Any, Dict, List, Optional

from hummingbot.core.data_type.order_book import OrderBook
from hummingbot.core.data_type.order_book_tracker_data_source import OrderBookTrackerDataSource
from hummingbot.logger import HummingbotLogger

from .stellar_client import StellarClient
from .stellar_constants import ORDER_BOOK_POLL_INTERVAL, TRADE_POLL_INTERVAL
from .stellar_order_book import StellarOrderBook
from .stellar_utils import get_asset_from_symbol, split_trading_pair

logger = logging.getLogger(__name__)


class StellarAPIOrderBookDataSource(OrderBookTrackerDataSource):
    """
    Data source for Stellar DEX order books.
    Provides snapshots, diffs, and trade streams.
    """

    _logger: Optional[HummingbotLogger] = None

    def __init__(self, trading_pairs: List[str], client: StellarClient):
        super().__init__(trading_pairs)
        self._client = client
        self._trading_pairs = trading_pairs
        self._trade_cursors: Dict[str, Optional[str]] = {pair: None for pair in trading_pairs}
        self._last_order_book_snapshots: Dict[str, Dict] = {}

    @classmethod
    def logger(cls) -> HummingbotLogger:
        if cls._logger is None:
            cls._logger = logging.getLogger(__name__)
        return cls._logger

    @classmethod
    async def get_last_traded_prices(cls, trading_pairs: List[str], client: StellarClient) -> Dict[str, float]:
        """Fetches the last traded price for specified trading pairs."""
        results = {}
        for trading_pair in trading_pairs:
            try:
                base_sym, quote_sym = split_trading_pair(trading_pair)
                base_asset = get_asset_from_symbol(base_sym)
                quote_asset = get_asset_from_symbol(quote_sym)
                trades = await client.get_trades(base_asset, quote_asset, limit=1)
                if trades:
                    trade = trades[0]
                    price_n = float(trade.get("price", {}).get("n", 0))
                    price_d = float(trade.get("price", {}).get("d", 1))
                    results[trading_pair] = price_n / price_d if price_d else 0.0
                else:
                    results[trading_pair] = 0.0
            except Exception as e:
                logger.error(f"Error fetching last price for {trading_pair}: {e}")
                results[trading_pair] = 0.0
        return results

    async def get_new_order_book(self, trading_pair: str) -> OrderBook:
        """Creates and populates a new order book from the current snapshot."""
        snapshot = await self.get_snapshot(trading_pair)
        snapshot_timestamp = time.time()

        snapshot_msg = StellarOrderBook.snapshot_message_from_exchange(snapshot, snapshot_timestamp, metadata={"trading_pair": trading_pair})

        order_book = self.order_book_create_function()
        order_book.apply_snapshot(snapshot_msg.bids, snapshot_msg.asks, snapshot_msg.update_id)
        return order_book

    async def get_snapshot(self, trading_pair: str) -> Dict[str, Any]:
        """Fetches the current DEX orderbook snapshot."""
        base_sym, quote_sym = split_trading_pair(trading_pair)
        base_asset = get_asset_from_symbol(base_sym)
        quote_asset = get_asset_from_symbol(quote_sym)

        data = await self._client.get_order_book(base_asset, quote_asset)

        snapshot = {
            "trading_pair": trading_pair,
            "update_id": int(time.time() * 1000),
            "bids": data["bids"],
            "asks": data["asks"],
        }

        self._last_order_book_snapshots[trading_pair] = snapshot
        return snapshot

    async def listen_for_trades(self, ev_loop: asyncio.AbstractEventLoop, output: asyncio.Queue):
        """
        Listens for trades by polling the Stellar network.
        Uses cursor-based pagination to get only new trades.
        """
        while True:
            try:
                for trading_pair in self._trading_pairs:
                    base_sym, quote_sym = split_trading_pair(trading_pair)
                    base_asset = get_asset_from_symbol(base_sym)
                    quote_asset = get_asset_from_symbol(quote_sym)

                    cursor = self._trade_cursors[trading_pair]
                    trades = await self._client.get_trades(base_asset, quote_asset, cursor=cursor, order="asc")

                    for trade in trades:
                        price_n = float(trade.get("price", {}).get("n", 0))
                        price_d = float(trade.get("price", {}).get("d", 1))
                        price = price_n / price_d if price_d else 0.0
                        trade_timestamp = time.time()

                        trade_msg = StellarOrderBook.trade_message_from_exchange(
                            {
                                "trade_id": trade.get("id", ""),
                                "trading_pair": trading_pair,
                                "price": price,
                                "amount": float(trade.get("base_amount", 0)),
                                "trade_type": (float("1") if trade.get("base_is_seller") else float("2")),
                                "update_id": trade_timestamp,
                            },
                            timestamp=trade_timestamp,
                            metadata={"trading_pair": trading_pair},
                        )
                        output.put_nowait(trade_msg)
                        self._trade_cursors[trading_pair] = trade.get("paging_token")

                await asyncio.sleep(TRADE_POLL_INTERVAL)

            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.error(f"Error listening for trades: {e}", exc_info=True)
                await asyncio.sleep(TRADE_POLL_INTERVAL * 2)

    async def listen_for_subscriptions(self):
        """
        Stellar does not have a websocket connection.
        Override base class method to avoid NotImplementedError.
        """

    async def listen_for_order_book_diffs(self, ev_loop: asyncio.AbstractEventLoop, output: asyncio.Queue):
        """
        Listens for order book changes by periodically fetching snapshots.
        Stellar does not provide a native diff stream via RPC,
        so we poll snapshots and emit them as updates.
        """
        while True:
            try:
                # Stellar does not have a websocket diff stream.
                # Hummingbot handles REST-only orderbooks by relying entirely on snapshots.
                await asyncio.sleep(ORDER_BOOK_POLL_INTERVAL * 10)

            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.error(f"Error listening for order book diffs: {e}", exc_info=True)
                await asyncio.sleep(ORDER_BOOK_POLL_INTERVAL * 2)

    async def listen_for_order_book_snapshots(self, ev_loop: asyncio.AbstractEventLoop, output: asyncio.Queue):
        """
        Periodically fetches full order book snapshots for sync.
        Uses a longer interval than diffs.
        """
        while True:
            try:
                for trading_pair in self._trading_pairs:
                    snapshot = await self.get_snapshot(trading_pair)
                    snapshot_timestamp = time.time()

                    msg = StellarOrderBook.snapshot_message_from_exchange(
                        snapshot,
                        snapshot_timestamp,
                        metadata={"trading_pair": trading_pair},
                    )
                    output.put_nowait(msg)

                await asyncio.sleep(ORDER_BOOK_POLL_INTERVAL * 10)

            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.error(f"Error in order book snapshots: {e}", exc_info=True)
                await asyncio.sleep(ORDER_BOOK_POLL_INTERVAL * 10)

    async def subscribe_to_trading_pair(self, trading_pair: str) -> bool:
        """
        Dynamically adds a trading pair to tracking.
        """
        if trading_pair not in self._trading_pairs:
            self._trading_pairs.append(trading_pair)
            self._trade_cursors[trading_pair] = None
        return True

    async def unsubscribe_from_trading_pair(self, trading_pair: str) -> bool:
        """
        Removes a trading pair from tracking.
        """
        if trading_pair in self._trading_pairs:
            self._trading_pairs.remove(trading_pair)
            self._trade_cursors.pop(trading_pair, None)
            self._last_order_book_snapshots.pop(trading_pair, None)
        return True
