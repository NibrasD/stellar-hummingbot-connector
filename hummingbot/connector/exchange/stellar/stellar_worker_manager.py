# hummingbot/connector/exchange/stellar/stellar_worker_manager.py
"""
Worker manager that coordinates all background workers for the Stellar connector.
Manages orderbook polling, trade listening, balance updates, and user stream workers.
"""

import asyncio
import logging
from typing import Dict, Optional

from .stellar_worker_pool import StellarWorkerPool

logger = logging.getLogger(__name__)


class StellarWorkerManager:
    """
    Coordinates all background tasks for the Stellar connector.
    Manages lifecycle of:
    - Order book polling workers
    - Trade listener workers
    - Balance update workers
    - User stream workers
    - Transaction pipeline workers
    """

    def __init__(self):
        self._pools: Dict[str, StellarWorkerPool] = {}
        self._tasks: Dict[str, asyncio.Task] = {}
        self._running = False

    @property
    def is_running(self) -> bool:
        return self._running

    def create_pool(self, name: str, pool_size: int = 3) -> StellarWorkerPool:
        """Creates and registers a named worker pool."""
        pool = StellarWorkerPool(pool_size=pool_size, name=name)
        self._pools[name] = pool
        return pool

    def get_pool(self, name: str) -> Optional[StellarWorkerPool]:
        """Gets a registered worker pool by name."""
        return self._pools.get(name)

    def register_task(self, name: str, coro):
        """Registers an async task to be managed."""
        if name in self._tasks and not self._tasks[name].done():
            self._tasks[name].cancel()
        task = asyncio.create_task(coro)
        self._tasks[name] = task
        logger.debug(f"Registered task: {name}")
        return task

    async def start_all(self):
        """Starts all registered pools."""
        self._running = True
        for name, pool in self._pools.items():
            await pool.start()
            logger.info(f"Started pool: {name}")

    async def stop_all(self):
        """Stops all registered pools and tasks."""
        self._running = False

        # Stop all pools
        for name, pool in self._pools.items():
            await pool.stop()
            logger.info(f"Stopped pool: {name}")

        # Cancel all registered tasks
        for name, task in self._tasks.items():
            if not task.done():
                task.cancel()
                logger.debug(f"Cancelled task: {name}")

        if self._tasks:
            await asyncio.gather(*self._tasks.values(), return_exceptions=True)

        self._tasks.clear()
        logger.info("Worker manager stopped")

    def get_status(self) -> Dict[str, any]:
        """Returns status of all managed pools and tasks."""
        status = {
            "running": self._running,
            "pools": {},
            "tasks": {},
        }
        for name, pool in self._pools.items():
            status["pools"][name] = {
                "running": pool.is_running,
                "pool_size": pool.pool_size,
                "pending": pool.pending_tasks,
            }
        for name, task in self._tasks.items():
            status["tasks"][name] = {
                "done": task.done(),
                "cancelled": task.cancelled(),
            }
        return status
