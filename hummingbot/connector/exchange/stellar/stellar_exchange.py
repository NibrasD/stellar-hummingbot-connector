# hummingbot/connector/exchange/stellar/stellar_exchange.py
"""
Main Stellar DEX Exchange connector for Hummingbot.
Implements the ExchangePyBase interface for full integration with
Hummingbot's strategy and order management system.

Architecture follows the XRPL connector reference pattern.
"""

import asyncio
import logging
import time
from decimal import Decimal
from typing import Any, Dict, List, Tuple

from bidict import bidict
from hummingbot.connector.exchange_py_base import ExchangePyBase
from hummingbot.connector.trading_rule import TradingRule
from hummingbot.core.data_type.common import OrderType, TradeType
from hummingbot.core.data_type.in_flight_order import InFlightOrder, OrderState, OrderUpdate, TradeUpdate
from hummingbot.core.data_type.order_book import OrderBook
from hummingbot.core.data_type.order_book_tracker_data_source import OrderBookTrackerDataSource
from hummingbot.core.data_type.trade_fee import AddedToCostTradeFee, TokenAmount, TradeFeeBase
from hummingbot.core.data_type.user_stream_tracker_data_source import UserStreamTrackerDataSource
from hummingbot.core.network_iterator import NetworkStatus

from .stellar_api_order_book_data_source import StellarAPIOrderBookDataSource
from .stellar_api_user_stream_data_source import StellarAPIUserStreamDataSource
from .stellar_auth import StellarAuth
from .stellar_client import StellarClient
from .stellar_constants import EXCHANGE_NAME, RATE_LIMITS
from .stellar_fill_processor import StellarFillProcessor
from .stellar_order_placement_strategy import StellarOrderPlacementStrategy
from .stellar_transaction_pipeline import StellarTransactionPipeline, TransactionRequest, TransactionStatus
from .stellar_utils import get_asset_from_symbol, set_network, split_trading_pair
from .stellar_worker_manager import StellarWorkerManager

logger = logging.getLogger(__name__)


class StellarExchange(ExchangePyBase):
    """
    Stellar DEX Exchange connector.

    Provides full exchange functionality:
    - Order placement and cancellation on the Stellar DEX
    - Order book tracking
    - Trade fill detection
    - Balance management
    - Parallel transaction submission via channel accounts

    Uses Soroban RPC as the primary network interface.
    """

    def __init__(
        self,
        client_config_map: Any = None,
        stellar_rpc_url: str = "",
        stellar_master_secret: str = "",
        stellar_channel_secrets: str = "",
        stellar_network: str = "PUBLIC",
        trading_pairs: List[str] = None,
        trading_required: bool = True,
        **kwargs,
    ):
        self._stellar_rpc_url = stellar_rpc_url
        self._stellar_network = stellar_network
        self._trading_pairs = trading_pairs or []
        self._trading_required = trading_required

        # Set network for asset resolution
        set_network(stellar_network)

        # Parse channel secrets
        channel_list = [s.strip() for s in stellar_channel_secrets.split(",") if s.strip()] if stellar_channel_secrets else []

        # Core components
        self._auth = StellarAuth(
            master_secret=stellar_master_secret,
            channel_secrets=channel_list,
            network=stellar_network,
        )
        self._client = StellarClient(rpc_url=stellar_rpc_url, network=stellar_network)
        self._pipeline = StellarTransactionPipeline(self._auth, self._client)
        self._placement_strategy = StellarOrderPlacementStrategy(self._auth, self._client, self._pipeline)
        self._fill_processor = StellarFillProcessor()
        self._worker_manager = StellarWorkerManager()

        # Order tracking
        self._in_flight_orders: Dict[str, InFlightOrder] = {}
        self._order_id_to_exchange_id: Dict[str, str] = {}
        self._exchange_id_to_order_id: Dict[str, str] = {}
        self._cancellation_in_progress: set = set()

        # Balance cache
        self._account_balances: Dict[str, Decimal] = {}
        self._account_available_balances: Dict[str, Decimal] = {}

        # State
        self._ready = False
        self._last_balance_poll_ts = 0

        # Filter kwargs to only what ExchangePyBase accepts to prevent unexpected keyword errors
        allowed_kwargs = ["balance_asset_limit", "rate_limits_share_pct"]
        filtered_kwargs = {k: v for k, v in kwargs.items() if k in allowed_kwargs}
        super().__init__(**filtered_kwargs)

    # ══════════════════════════════════════════
    # ExchangePyBase Required Properties
    # ══════════════════════════════════════════

    @property
    def name(self) -> str:
        return EXCHANGE_NAME

    @property
    def authenticator(self):
        return self._auth

    @property
    def rate_limits_rules(self):
        return RATE_LIMITS

    @property
    def domain(self) -> str:
        return self._stellar_network.lower()

    @property
    def client_order_id_max_length(self) -> int:
        return 64

    @property
    def client_order_id_prefix(self) -> str:
        return "stellar"

    @property
    def trading_pairs(self) -> List[str]:
        return self._trading_pairs

    @property
    def is_cancel_request_in_exchange_synchronous(self) -> bool:
        return False  # Stellar txs are asynchronous

    @property
    def is_trading_required(self) -> bool:
        return self._trading_required

    @property
    def check_network_request_path(self) -> str:
        return ""  # We use custom network check

    async def _make_network_check_request(self):
        """Override to use RPC instead of REST for network check."""
        await self._client.check_connection()

    @property
    def trading_pairs_request_path(self) -> str:
        return ""

    @property
    def trading_rules_request_path(self) -> str:
        return ""

    def supported_order_types(self) -> List[OrderType]:
        return [OrderType.LIMIT, OrderType.LIMIT_MAKER]

    @property
    def status_dict(self) -> Dict[str, bool]:
        return {
            "network_connected": self._client.is_connected,
            "order_books_initialized": self.order_book_tracker.ready,
            "account_balance_fetched": len(self._account_balances) > 0,
            "trading_rule_initialized": len(self._trading_rules) > 0,
        }

    @property
    def ready(self) -> bool:
        return all(self.status_dict.values())

    # ══════════════════════════════════════════
    # Network & Lifecycle
    # ══════════════════════════════════════════

    async def start_network(self):
        """Initialize network connections and start background workers."""
        await super().start_network()
        await self._client.check_connection()
        await self._pipeline.start()
        await self._update_balances()
        self._ready = True
        logger.info("Stellar connector network started")

    async def stop_network(self):
        """Stop all background workers and close connections."""
        # Force eager cancellation of active orders before shutdown
        open_orders = [o for o in self._in_flight_orders.values() if not o.is_done]
        if open_orders:
            logger.info(f"Eagerly cancelling {len(open_orders)} active orders during network shutdown...")
            for order in open_orders:
                await self._place_cancel(order.client_order_id, order)

        await super().stop_network()
        await self._pipeline.stop()
        await self._worker_manager.stop_all()
        self._ready = False
        logger.info("Stellar connector network stopped")

    async def check_network(self) -> NetworkStatus:
        """Check if the network is reachable."""
        try:
            connected = await self._client.check_connection()
            return NetworkStatus.CONNECTED if connected else NetworkStatus.NOT_CONNECTED
        except Exception:
            return NetworkStatus.NOT_CONNECTED

    async def _update_time_synchronizer(self, pass_on_non_cancelled_error: bool = False):
        """
        Override: Stellar does not have a REST time endpoint.
        The base class tries to call web_utils.get_current_server_time()
        which doesn't exist for this connector. We skip time sync entirely
        since Stellar transactions use sequence numbers, not timestamps.
        """

    # ══════════════════════════════════════════
    # Data Source Factories
    # ══════════════════════════════════════════

    def _create_order_book_data_source(self) -> OrderBookTrackerDataSource:
        return StellarAPIOrderBookDataSource(
            trading_pairs=self._trading_pairs,
            client=self._client,
        )

    def _create_user_stream_data_source(self) -> UserStreamTrackerDataSource:
        return StellarAPIUserStreamDataSource(
            auth=self._auth,
            client=self._client,
            trading_pairs=self._trading_pairs,
        )

    # ══════════════════════════════════════════
    # Order Management
    # ══════════════════════════════════════════

    async def _place_order(
        self,
        order_id: str,
        trading_pair: str,
        amount: Decimal,
        trade_type: TradeType,
        order_type: OrderType,
        price: Decimal,
        **kwargs,
    ) -> Tuple[str, float]:
        """
        Places an order on the Stellar DEX.

        Returns (exchange_order_id, timestamp).
        """
        base_sym, quote_sym = split_trading_pair(trading_pair)
        base_asset = get_asset_from_symbol(base_sym)
        quote_asset = get_asset_from_symbol(quote_sym)

        is_buy = trade_type == TradeType.BUY

        if is_buy:
            selling = quote_asset
            buying = base_asset
        else:
            selling = base_asset
            buying = quote_asset

        # Create the in-flight order
        in_flight_order = InFlightOrder(
            client_order_id=order_id,
            exchange_order_id=None,
            trading_pair=trading_pair,
            order_type=order_type,
            trade_type=trade_type,
            amount=amount,
            price=price,
            creation_timestamp=time.time(),
        )
        self._in_flight_orders[order_id] = in_flight_order

        # Define callback for when transaction completes
        async def on_tx_complete(tx_request: TransactionRequest):
            await self._process_order_result(order_id, tx_request)

        # Submit via placement strategy
        await self._placement_strategy.place_order(
            request_id=order_id,
            selling=selling,
            buying=buying,
            amount=amount,
            price=price,
            is_buy=is_buy,
            callback=on_tx_complete,
        )

        return order_id, time.time()

    async def _place_cancel(self, order_id: str, tracked_order: InFlightOrder):
        """
        Cancels an order on the Stellar DEX.
        """
        if order_id in self._cancellation_in_progress:
            logger.info(f"Cancel for {order_id} already in progress, skipping duplicate request.")
            return False

        self._cancellation_in_progress.add(order_id)
        try:
            logger.info(f"Received cancellation request for {order_id} from Hummingbot core")
            exchange_order_id = tracked_order.exchange_order_id
            if not exchange_order_id:
                logger.warning(f"Cannot cancel {order_id}: no exchange order ID")
                return False

            base_sym, quote_sym = split_trading_pair(tracked_order.trading_pair)
            base_asset = get_asset_from_symbol(base_sym)
            quote_asset = get_asset_from_symbol(quote_sym)

            if tracked_order.trade_type == TradeType.SELL:
                selling = base_asset
                buying = quote_asset
            else:
                selling = quote_asset
                buying = base_asset

            async def on_cancel_complete(tx_request: TransactionRequest):
                if tx_request.status == TransactionStatus.SUCCESS:
                    self._order_tracker.process_order_update(
                        OrderUpdate(
                            client_order_id=order_id,
                            exchange_order_id=exchange_order_id,
                            trading_pair=tracked_order.trading_pair,
                            update_timestamp=time.time(),
                            new_state=OrderState.CANCELED,
                        )
                    )
                    logger.info(f"Order {order_id} cancelled successfully")
                else:
                    logger.error(f"Failed to cancel order {order_id}: {tx_request.error}")

            await self._placement_strategy.cancel_order(
                request_id=order_id,
                selling=selling,
                buying=buying,
                offer_id=int(exchange_order_id),
                callback=on_cancel_complete,
            )

            return True
        except Exception as e:
            logger.error(f"Error submitting cancellation for {order_id}: {e}")
            self._cancellation_in_progress.discard(order_id)
            return False

    async def _process_order_result(self, order_id: str, tx_request: TransactionRequest):
        """
        Processes the result of an order placement transaction.
        """
        order = self._in_flight_orders.get(order_id)
        if not order:
            return

        if tx_request.status == TransactionStatus.SUCCESS:
            result = tx_request.result or {}
            exchange_order_id = str(result.get("offer_id", tx_request.tx_hash or ""))

            # Map order IDs
            self._order_id_to_exchange_id[order_id] = exchange_order_id
            self._exchange_id_to_order_id[exchange_order_id] = order_id

            # Update order state
            order.exchange_order_id = exchange_order_id

            # Process any immediate fills
            fills = self._fill_processor.process_transaction_result(order, result, tx_request.tx_hash or "")

            if fills:
                for fill in fills:
                    self._order_tracker.process_trade_update(fill)

            # Determine new state
            if result.get("offer_id"):
                # Offer is resting on the book (may be partially filled)
                new_state = OrderState.OPEN
            elif fills and not result.get("offer_id"):
                # Fully filled immediately (no resting offer created)
                new_state = OrderState.FILLED
            else:
                new_state = OrderState.OPEN

            self._order_tracker.process_order_update(
                OrderUpdate(
                    client_order_id=order_id,
                    exchange_order_id=exchange_order_id,
                    trading_pair=order.trading_pair,
                    update_timestamp=time.time(),
                    new_state=new_state,
                )
            )

            logger.info(f"Order {order_id} processed: exchange_id={exchange_order_id}, " f"state={new_state.name}, fills={len(fills)}")

        else:
            # Transaction failed
            self._order_tracker.process_order_update(
                OrderUpdate(
                    client_order_id=order_id,
                    exchange_order_id="",
                    trading_pair=order.trading_pair,
                    update_timestamp=time.time(),
                    new_state=OrderState.FAILED,
                )
            )
            logger.error(f"Order {order_id} failed: {tx_request.error}")

    # ══════════════════════════════════════════
    # Balance Management
    # ══════════════════════════════════════════

    async def _update_balances(self):
        """Fetches and updates account balances."""
        try:
            account_id = self._auth.master_public_key
            balances = await self._client.get_balances(account_id)

            self._account_balances.clear()
            self._account_available_balances.clear()

            for asset_code, balance in balances.items():
                self._account_balances[asset_code] = balance
                # Available = total - reserved for open orders
                self._account_available_balances[asset_code] = balance

            self._last_balance_poll_ts = time.time()

        except Exception as e:
            logger.error(f"Error updating balances: {e}", exc_info=True)

    def _get_balance(self, currency: str) -> Decimal:
        """Gets the total balance for a currency."""
        return self._account_balances.get(currency, Decimal(0))

    def _get_available_balance(self, currency: str) -> Decimal:
        """Gets the available (non-reserved) balance for a currency."""
        return self._account_available_balances.get(currency, Decimal(0))

    # ══════════════════════════════════════════
    # Trade Fees
    # ══════════════════════════════════════════

    def _get_fee(
        self,
        base_currency: str,
        quote_currency: str,
        order_type: OrderType,
        order_side: TradeType,
        amount: Decimal,
        price: Decimal,
        is_maker: bool = None,
    ) -> TradeFeeBase:
        """
        Returns the trade fee for an order.
        Stellar DEX has zero maker/taker fees — only network transaction fees.
        """
        return AddedToCostTradeFee(
            percent=Decimal(0),
            flat_fees=[TokenAmount(token="XLM", amount=Decimal("0.00001"))],
        )

    # ══════════════════════════════════════════
    # Order Book & Status
    # ══════════════════════════════════════════

    async def _update_trading_rules(self):
        """
        Stellar DEX has no server-side trading rules to fetch.
        All assets can be traded with any precision, so we inject universal rules
        to prevent Cython segmentation faults from missing rules in Strategies.
        """
        self._trading_rules.clear()
        for trading_pair in self._trading_pairs:
            self._trading_rules[trading_pair] = TradingRule(
                trading_pair=trading_pair,
                min_order_size=Decimal("0.0000001"),
                min_price_increment=Decimal("0.0000001"),
                min_base_amount_increment=Decimal("0.0000001"),
                min_notional_size=Decimal("0.0000001"),
            )

    async def _format_trading_rules(self, raw_trading_rules: Any):
        """No trading rules to format for Stellar DEX."""
        return []

    async def _update_order_status(self):
        """
        Checks the status of all in-flight orders on the ledger.
        """
        for order_id, order in list(self._in_flight_orders.items()):
            if order.is_done or not order.exchange_order_id:
                continue

            try:
                # Check if offer still exists on the ledger
                offer = await self._client.get_offer(
                    self._auth.master_public_key,
                    int(order.exchange_order_id),
                )

                if offer is None:
                    # Offer is gone — either filled or externally cancelled
                    if order.current_state == OrderState.OPEN:
                        self._order_tracker.process_order_update(
                            OrderUpdate(
                                client_order_id=order_id,
                                exchange_order_id=order.exchange_order_id,
                                trading_pair=order.trading_pair,
                                update_timestamp=time.time(),
                                new_state=OrderState.FILLED,
                            )
                        )
                else:
                    # Check for partial fills (amount decreased)
                    remaining = offer.get("amount", Decimal(0))
                    if remaining < order.amount:

                        self._order_tracker.process_order_update(
                            OrderUpdate(
                                client_order_id=order_id,
                                exchange_order_id=order.exchange_order_id,
                                trading_pair=order.trading_pair,
                                update_timestamp=time.time(),
                                new_state=OrderState.PARTIALLY_FILLED,
                            )
                        )

            except Exception as e:
                logger.warning(f"Error checking order {order_id} status: {e}")

    async def _all_trade_updates_for_order(self, order: InFlightOrder) -> List[TradeUpdate]:
        """Returns all trade updates for a given order."""
        return []

    async def _request_order_status(self, tracked_order: InFlightOrder) -> OrderUpdate:
        """Requests the current status of an order from the exchange."""
        exchange_order_id = tracked_order.exchange_order_id
        if not exchange_order_id:
            return OrderUpdate(
                client_order_id=tracked_order.client_order_id,
                exchange_order_id="",
                trading_pair=tracked_order.trading_pair,
                update_timestamp=time.time(),
                new_state=OrderState.PENDING_CREATE,
            )

        offer = await self._client.get_offer(
            self._auth.master_public_key,
            int(exchange_order_id),
        )

        if offer:
            new_state = OrderState.OPEN
        else:
            new_state = OrderState.FILLED  # Offer gone = filled or cancelled

        return OrderUpdate(
            client_order_id=tracked_order.client_order_id,
            exchange_order_id=exchange_order_id,
            trading_pair=tracked_order.trading_pair,
            update_timestamp=time.time(),
            new_state=new_state,
        )

    # ══════════════════════════════════════════
    # Convenience Methods
    # ══════════════════════════════════════════

    def buy(
        self,
        trading_pair: str,
        amount: Decimal,
        order_type: OrderType,
        price: Decimal,
        **kwargs,
    ) -> str:
        """Places a buy order."""
        order_id = self.client_order_id_prefix + f"_buy_{int(time.time() * 1000)}"
        safe_ensure_future(self._place_order(order_id, trading_pair, amount, TradeType.BUY, order_type, price, **kwargs))
        return order_id

    def sell(
        self,
        trading_pair: str,
        amount: Decimal,
        order_type: OrderType,
        price: Decimal,
        **kwargs,
    ) -> str:
        """Places a sell order."""
        order_id = self.client_order_id_prefix + f"_sell_{int(time.time() * 1000)}"
        safe_ensure_future(self._place_order(order_id, trading_pair, amount, TradeType.SELL, order_type, price, **kwargs))
        return order_id

    def cancel(self, trading_pair: str, order_id: str) -> str:
        """Cancels an order."""
        tracked_order = self._in_flight_orders.get(order_id)
        if tracked_order:
            safe_ensure_future(self._place_cancel(order_id, tracked_order))
        else:
            logger.warning(f"Order {order_id} not found in in-flight orders")
        return order_id

    def get_order_book(self, trading_pair: str) -> OrderBook:
        """Returns the order book for a trading pair."""
        return self.order_book_tracker.order_books.get(trading_pair)

    def get_balance(self, currency: str) -> Decimal:
        """Returns the balance for a currency."""
        return self._get_balance(currency)

    def get_available_balance(self, currency: str) -> Decimal:
        """Returns the available balance for a currency."""
        return self._get_available_balance(currency)

    def format_status(self) -> str:
        """Returns a formatted status string for the connector."""
        lines = []
        lines.append("\n  Stellar DEX Connector Status")
        lines.append("  ═══════════════════════════")
        lines.append(f"  Network:    {self._stellar_network}")
        lines.append(f"  RPC URL:    {self._stellar_rpc_url}")
        lines.append(f"  Connected:  {self._client.is_connected}")
        lines.append(f"  Channels:   {self._auth.num_channels}")
        lines.append(f"  Account:    {self._auth.master_public_key[:12]}...")

        if self._account_balances:
            lines.append("\n  Balances:")
            for asset, balance in sorted(self._account_balances.items()):
                lines.append(f"    {asset}: {balance}")

        in_flight = [o for o in self._in_flight_orders.values() if not o.is_done]
        if in_flight:
            lines.append(f"\n  Open Orders: {len(in_flight)}")
            for order in in_flight:
                lines.append(f"    {order.trade_type.name} {order.amount} {order.trading_pair} " f"@ {order.price} [{order.current_state.name}]")

        return "\n".join(lines)

    # ══════════════════════════════════════════
    # Base Class Method Overrides
    # ══════════════════════════════════════════

    def _create_web_assistants_factory(self) -> Any:
        """Not required since Soroban RPC handles networking."""
        return None

    def _initialize_trading_pair_symbols_from_exchange_info(self, exchange_info: Any):
        """Stellar assets do not require pre-fetching symbol mappings. We map 1:1."""
        mapping = bidict()
        for pair in self._trading_pairs:
            mapping[pair] = pair
        self._set_trading_pair_symbol_map(mapping)

    async def _make_trading_pairs_request(self) -> Any:
        """Stellar assets do not require pre-fetching pair mappings."""
        return []

    async def _make_trading_rules_request(self) -> Any:
        """Stellar rules are static, handled by _update_trading_rules."""
        return []

    def _is_order_not_found_during_cancelation_error(self, cancelation_exception: Exception) -> bool:
        return False

    def _is_order_not_found_during_status_update_error(self, status_update_exception: Exception) -> bool:
        return False

    def _is_request_exception_related_to_time_synchronizer(self, request_exception: Exception) -> bool:
        return False

    async def _update_trading_fees(self):
        """Stellar DEX network fees are static and predictable."""

    async def _user_stream_event_listener(self):
        """Stellar User Stream is handled natively by the Data Source."""


def safe_ensure_future(coro):
    """Safely creates an asyncio task."""
    try:
        loop = asyncio.get_running_loop()
        return loop.create_task(coro)
    except RuntimeError:
        return asyncio.ensure_future(coro)
