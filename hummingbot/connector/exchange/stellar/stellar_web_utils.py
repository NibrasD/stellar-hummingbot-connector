# hummingbot/connector/exchange/stellar/stellar_web_utils.py
"""
Web utilities for the Stellar connector.
Provides HTTP and RPC communication helpers using aiohttp.
"""

import asyncio
import logging
from typing import Any, Dict, Optional

import aiohttp

logger = logging.getLogger(__name__)


async def rpc_request(
    rpc_url: str,
    method: str,
    params: Optional[Dict[str, Any]] = None,
    request_id: int = 1,
    timeout: float = 30.0,
) -> Dict[str, Any]:
    """
    Makes a JSON-RPC 2.0 request to a Soroban RPC endpoint.

    Args:
        rpc_url: The Soroban RPC endpoint URL.
        method: The RPC method name (e.g., "sendTransaction").
        params: Optional dictionary of parameters.
        request_id: JSON-RPC request ID.
        timeout: Request timeout in seconds.

    Returns:
        The "result" field from the JSON-RPC response.

    Raises:
        Exception: If the RPC returns an error.
    """
    payload = {
        "jsonrpc": "2.0",
        "id": request_id,
        "method": method,
        "params": params or {},
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                rpc_url,
                json=payload,
                headers={
                    "Content-Type": "application/json",
                    "User-Agent": "StellarHummingbot/1.0",
                },
                timeout=aiohttp.ClientTimeout(total=timeout),
            ) as response:
                response.raise_for_status()
                result = await response.json()

                if "error" in result:
                    error = result["error"]
                    error_msg = error.get("message", str(error))
                    error_code = error.get("code", "unknown")
                    raise RPCError(
                        f"RPC Error [{error_code}]: {error_msg}",
                        code=error_code,
                        data=error.get("data"),
                    )

                return result.get("result", {})

    except aiohttp.ClientError as e:
        raise ConnectionError(f"Failed to connect to RPC at {rpc_url}: {e}") from e
    except asyncio.TimeoutError:
        raise TimeoutError(f"RPC request to {rpc_url} method={method} timed out after {timeout}s")


async def rpc_request_with_retry(
    rpc_url: str,
    method: str,
    params: Optional[Dict[str, Any]] = None,
    max_retries: int = 3,
    retry_delay: float = 1.0,
    timeout: float = 30.0,
) -> Dict[str, Any]:
    """
    Makes an RPC request with exponential backoff retry logic.
    """
    last_error = None
    for attempt in range(max_retries):
        try:
            return await rpc_request(rpc_url, method, params, timeout=timeout)
        except (ConnectionError, TimeoutError) as e:
            last_error = e
            if attempt < max_retries - 1:
                delay = retry_delay * (2**attempt)
                logger.warning(f"RPC request failed (attempt {attempt + 1}/{max_retries}), " f"retrying in {delay}s: {e}")
                await asyncio.sleep(delay)
            else:
                raise
        except RPCError:
            raise  # Don't retry RPC-level errors

    raise last_error


async def horizon_request(
    horizon_url: str,
    path: str,
    params: Optional[Dict[str, str]] = None,
    timeout: float = 30.0,
) -> Dict[str, Any]:
    """
    Makes an HTTP GET request to a Horizon endpoint.
    Used as fallback for features not yet supported by Soroban RPC.
    """
    url = f"{horizon_url}{path}"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                url,
                params=params,
                timeout=aiohttp.ClientTimeout(total=timeout),
            ) as response:
                response.raise_for_status()
                return await response.json()
    except aiohttp.ClientError as e:
        raise ConnectionError(f"Horizon request failed: {url}: {e}") from e


class RPCError(Exception):
    """Custom exception for Soroban RPC errors."""

    def __init__(self, message: str, code: Any = None, data: Any = None):
        super().__init__(message)
        self.code = code
        self.data = data
