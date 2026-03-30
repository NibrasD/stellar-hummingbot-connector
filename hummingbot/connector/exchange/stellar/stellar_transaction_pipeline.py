# hummingbot/connector/exchange/stellar/stellar_transaction_pipeline.py
"""
Transaction pipeline for the Stellar connector.
Queues, sequences, and manages the lifecycle of Stellar transactions.
Handles parallel submission via channel accounts with automatic retry on
sequence number conflicts.
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

from .stellar_auth import StellarAuth
from .stellar_client import StellarClient
from .stellar_constants import DEFAULT_BASE_FEE, TRANSACTION_TIMEOUT_SECONDS
from .stellar_xdr_utils import decode_transaction_result

logger = logging.getLogger(__name__)


class TransactionStatus(Enum):
    QUEUED = "queued"
    BUILDING = "building"
    SUBMITTING = "submitting"
    PENDING = "pending"
    SUCCESS = "success"
    FAILED = "failed"
    TIMEOUT = "timeout"
    RETRYING = "retrying"


@dataclass
class TransactionRequest:
    """Represents a transaction request in the pipeline."""

    request_id: str
    operations: list
    callback: Optional[Callable] = None
    memo: Optional[str] = None
    base_fee: int = DEFAULT_BASE_FEE
    max_retries: int = 3
    status: TransactionStatus = TransactionStatus.QUEUED
    result: Optional[Dict[str, Any]] = None
    tx_hash: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    attempts: int = 0
    error: Optional[str] = None


class StellarTransactionPipeline:
    """
    Manages the transaction lifecycle:
    1. Accepts transaction requests (operations to submit)
    2. Acquires channel accounts from the auth pool
    3. Builds, signs, and submits transactions
    4. Polls for confirmation
    5. Retries on sequence conflicts
    6. Reports results via callbacks
    """

    def __init__(self, auth: StellarAuth, client: StellarClient):
        self._auth = auth
        self._client = client
        self._queue: asyncio.Queue = asyncio.Queue()
        self._active_requests: Dict[str, TransactionRequest] = {}
        self._running = False
        self._workers: List[asyncio.Task] = []

    @property
    def pending_count(self) -> int:
        return self._queue.qsize() + len(self._active_requests)

    async def start(self, num_workers: int = None):
        """
        Starts the transaction pipeline with N worker tasks
        (one per channel account).
        """
        if self._running:
            return

        self._running = True
        num_workers = num_workers or self._auth.num_channels

        for i in range(num_workers):
            task = asyncio.create_task(self._worker_loop(i))
            self._workers.append(task)

        logger.info(f"Transaction pipeline started with {num_workers} workers")

    async def stop(self):
        """Stops the transaction pipeline."""
        # Yield event loop to allow freshly spawned _place_cancel tasks to enter the queue
        await asyncio.sleep(2.0)

        if len(self._active_requests) > 0:
            logger.info(f"Waiting for {len(self._active_requests)} pending transactions (e.g. cancellations) to complete...")
            wait_iters = 0
            while len(self._active_requests) > 0 and wait_iters < 30:
                await asyncio.sleep(1.0)
                wait_iters += 1

        self._running = False
        for task in self._workers:
            task.cancel()
        self._workers.clear()
        logger.info("Transaction pipeline stopped")

    async def submit(self, request: TransactionRequest) -> str:
        """
        Submits a transaction request to the pipeline.
        Returns the request_id for tracking.
        """
        self._active_requests[request.request_id] = request
        await self._queue.put(request)
        logger.debug(f"Transaction request queued: {request.request_id}")
        return request.request_id

    def get_request_status(self, request_id: str) -> Optional[TransactionRequest]:
        """Gets the current status of a transaction request."""
        return self._active_requests.get(request_id)

    async def _worker_loop(self, worker_id: int):
        """
        Worker loop that processes transaction requests.
        Each worker acquires its own channel account.
        """
        logger.debug(f"Transaction worker {worker_id} started")

        while self._running:
            try:
                request = await asyncio.wait_for(self._queue.get(), timeout=1.0)
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break

            channel_kp = None
            try:
                channel_kp = await self._auth.acquire_channel()
                await self._process_request(request, channel_kp)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Worker {worker_id} error: {e}", exc_info=True)
                request.status = TransactionStatus.FAILED
                request.error = str(e)
                if request.callback:
                    await self._safe_callback(request)
            finally:
                if channel_kp:
                    self._auth.release_channel(channel_kp)
                if request.request_id in self._active_requests:
                    del self._active_requests[request.request_id]

    async def _process_request(self, request: TransactionRequest, channel_kp):
        """
        Processes a single transaction request.
        Handles building, signing, submitting, and retry logic.
        """
        for attempt in range(request.max_retries):
            request.attempts = attempt + 1
            request.status = TransactionStatus.BUILDING

            try:
                # 1. Get sequence number
                seq_num = await self._auth.get_sequence_number(channel_kp, self._client)

                # 2. Build transaction
                tx_builder = self._auth.build_transaction(
                    channel_kp=channel_kp,
                    sequence=seq_num,
                    operations=request.operations,
                    base_fee=request.base_fee,
                    timeout=TRANSACTION_TIMEOUT_SECONDS,
                    memo=request.memo,
                )

                # 3. Sign transaction
                xdr_tx = self._auth.sign_transaction(tx_builder, channel_kp)

                # 4. Submit and wait
                request.status = TransactionStatus.SUBMITTING
                result = await self._client.submit_and_wait(xdr_tx)

                request.tx_hash = result.get("hash")
                tx_status = result.get("status", "")

                if tx_status == "SUCCESS":
                    # 5. Decode result
                    result_xdr = result.get("resultXdr", "")
                    if result_xdr:
                        decoded = decode_transaction_result(result_xdr)
                        request.result = decoded
                    else:
                        request.result = {"success": True}

                    request.status = TransactionStatus.SUCCESS
                    logger.info(f"Transaction {request.request_id} succeeded " f"(hash: {request.tx_hash[:12]}..., attempt {attempt + 1})")

                    if request.callback:
                        await self._safe_callback(request)
                    return

                elif tx_status == "FAILED":
                    error_msg = result.get("error", "Unknown failure")
                    # Check for sequence conflict
                    if "tx_bad_seq" in str(result.get("resultXdr", "")):
                        logger.warning(f"Sequence conflict for {request.request_id}, " f"refreshing and retrying...")
                        await self._auth.refresh_sequence_number(channel_kp, self._client)
                        request.status = TransactionStatus.RETRYING
                        continue

                    request.error = error_msg
                    request.status = TransactionStatus.FAILED
                    logger.error(f"Transaction {request.request_id} failed: {error_msg}")

                    if request.callback:
                        await self._safe_callback(request)
                    return

                else:
                    # Timeout or unknown
                    request.status = TransactionStatus.TIMEOUT
                    request.error = result.get("error", "Transaction timed out")
                    logger.warning(f"Transaction {request.request_id} timed out")

            except Exception as e:
                if "tx_bad_seq" in str(e) or "bad seq" in str(e).lower():
                    logger.warning(f"Sequence error, refreshing: {e}")
                    await self._auth.refresh_sequence_number(channel_kp, self._client)
                    request.status = TransactionStatus.RETRYING
                    continue

                if attempt < request.max_retries - 1:
                    logger.warning(f"Transaction {request.request_id} attempt {attempt + 1} failed: {e}. Retrying...")
                    await asyncio.sleep(1.0 * (attempt + 1))
                    continue
                else:
                    request.status = TransactionStatus.FAILED
                    request.error = str(e)

        # All retries exhausted
        if request.status != TransactionStatus.SUCCESS:
            request.status = TransactionStatus.FAILED
            if not request.error:
                request.error = "Max retries exceeded"
            logger.error(f"Transaction {request.request_id} failed after {request.max_retries} attempts")

        if request.callback:
            await self._safe_callback(request)

    async def _safe_callback(self, request: TransactionRequest):
        """Safely invoke callback without crashing the worker."""
        try:
            if asyncio.iscoroutinefunction(request.callback):
                await request.callback(request)
            else:
                request.callback(request)
        except Exception as e:
            logger.error(f"Callback error for {request.request_id}: {e}")
