# hummingbot/connector/exchange/stellar/stellar_worker_pool.py
"""
Worker pool for managing concurrent operations in the Stellar connector.
Provides a reusable pool of async workers for parallel task execution.
"""

import asyncio
import logging
from typing import Callable, Coroutine, List, Optional

logger = logging.getLogger(__name__)


class StellarWorkerPool:
    """
    A pool of async workers that process tasks concurrently.
    Used for parallel order book updates, balance refreshes, and trade polling.
    """

    def __init__(self, pool_size: int = 5, name: str = "StellarWorkerPool"):
        self._pool_size = pool_size
        self._name = name
        self._queue: asyncio.Queue = asyncio.Queue()
        self._workers: List[asyncio.Task] = []
        self._running = False

    @property
    def pool_size(self) -> int:
        return self._pool_size

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def pending_tasks(self) -> int:
        return self._queue.qsize()

    async def start(self):
        """Starts the worker pool."""
        if self._running:
            return

        self._running = True
        for i in range(self._pool_size):
            task = asyncio.create_task(self._worker_loop(i))
            self._workers.append(task)

        logger.info(f"{self._name} started with {self._pool_size} workers")

    async def stop(self):
        """Stops the worker pool gracefully."""
        self._running = False

        # Cancel all workers
        for task in self._workers:
            task.cancel()

        if self._workers:
            await asyncio.gather(*self._workers, return_exceptions=True)

        self._workers.clear()
        logger.info(f"{self._name} stopped")

    async def submit(
        self,
        coro: Coroutine,
        callback: Optional[Callable] = None,
        error_callback: Optional[Callable] = None,
    ):
        """
        Submits a coroutine to be executed by a worker.

        Args:
            coro: The coroutine to execute.
            callback: Optional callback invoked with the result on success.
            error_callback: Optional callback invoked with the exception on failure.
        """
        await self._queue.put((coro, callback, error_callback))

    async def _worker_loop(self, worker_id: int):
        """Worker loop that processes tasks from the queue."""
        while self._running:
            try:
                coro, callback, error_callback = await asyncio.wait_for(self._queue.get(), timeout=1.0)
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break

            try:
                result = await coro
                if callback:
                    if asyncio.iscoroutinefunction(callback):
                        await callback(result)
                    else:
                        callback(result)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"{self._name} worker {worker_id} task error: {e}", exc_info=True)
                if error_callback:
                    try:
                        if asyncio.iscoroutinefunction(error_callback):
                            await error_callback(e)
                        else:
                            error_callback(e)
                    except Exception as cb_err:
                        logger.error(f"Error callback failed: {cb_err}")
