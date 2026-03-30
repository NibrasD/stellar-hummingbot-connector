# hummingbot/connector/exchange/stellar/stellar_constants.py
"""
Constants and configuration for the Stellar DEX connector.
"""

from hummingbot.core.api_throttler.data_types import RateLimit

EXCHANGE_NAME = "stellar"
DEFAULT_DOMAIN = "public"

# ──────────────────────────────────────────────
# Soroban RPC Endpoints (PRIMARY — per RFP requirement)
# ──────────────────────────────────────────────
SOROBAN_RPC_URL_MAINNET = "https://soroban-rpc.mainnet.stellar.gateway.fm"
SOROBAN_RPC_URL_TESTNET = "https://soroban-testnet.stellar.org"

# Horizon (FALLBACK ONLY — used only when RPC does not support a feature)
HORIZON_URL_MAINNET = "https://horizon.stellar.org"
HORIZON_URL_TESTNET = "https://horizon-testnet.stellar.org"

# ──────────────────────────────────────────────
# Network Passphrases
# ──────────────────────────────────────────────
NETWORK_PASSPHRASE_PUBLIC = "Public Global Stellar Network ; September 2015"
NETWORK_PASSPHRASE_TESTNET = "Test SDF Network ; September 2015"

# ──────────────────────────────────────────────
# RPC Method Names
# ──────────────────────────────────────────────
RPC_SEND_TRANSACTION = "sendTransaction"
RPC_GET_TRANSACTION = "getTransaction"
RPC_GET_LEDGER_ENTRIES = "getLedgerEntries"
RPC_GET_EVENTS = "getEvents"
RPC_GET_LATEST_LEDGER = "getLatestLedger"
RPC_GET_NETWORK = "getNetwork"
RPC_SIMULATE_TRANSACTION = "simulateTransaction"

# ──────────────────────────────────────────────
# Transaction Constants
# ──────────────────────────────────────────────
DEFAULT_BASE_FEE = 100  # stroops
MAX_BASE_FEE = 10000  # stroops
TRANSACTION_TIMEOUT_SECONDS = 30
TRANSACTION_POLL_INTERVAL = 2.0
TRANSACTION_MAX_RETRIES = 15

# ──────────────────────────────────────────────
# Polling Intervals
# ──────────────────────────────────────────────
ORDER_BOOK_POLL_INTERVAL = 3.0  # seconds
TRADE_POLL_INTERVAL = 3.0  # seconds
BALANCE_POLL_INTERVAL = 10.0  # seconds
USER_STREAM_POLL_INTERVAL = 2.0  # seconds

# ──────────────────────────────────────────────
# Order States
# ──────────────────────────────────────────────
ORDER_STATE_PENDING_CREATE = "PendingCreate"
ORDER_STATE_OPEN = "Open"
ORDER_STATE_PARTIALLY_FILLED = "PartiallyFilled"
ORDER_STATE_FILLED = "Filled"
ORDER_STATE_PENDING_CANCEL = "PendingCancel"
ORDER_STATE_CANCELED = "Canceled"
ORDER_STATE_FAILED = "Failed"

# ──────────────────────────────────────────────
# Rate Limits
# ──────────────────────────────────────────────
STELLAR_RPC_RATE_LIMIT_ID = "stellar_rpc"
STELLAR_GENERAL_RATE_LIMIT_ID = "stellar_general"

RATE_LIMITS = [
    RateLimit(limit_id=STELLAR_RPC_RATE_LIMIT_ID, limit=30, time_interval=1),
    RateLimit(limit_id=STELLAR_GENERAL_RATE_LIMIT_ID, limit=10, time_interval=1),
]

# ──────────────────────────────────────────────
# Supported Soroban AMM Contracts (Optional Advanced Feature)
# ──────────────────────────────────────────────
SOROSWAP_ROUTER_CONTRACT_MAINNET = "CDKDFC5GAVHPNBAJZ43V4ALAFE6OHECIIFV5AH4UI5VMT5LZXGLHQMAA"
AQUARIUS_ROUTER_CONTRACT_MAINNET = ""  # TBD when available

# ──────────────────────────────────────────────
# Asset Constants
# ──────────────────────────────────────────────
NATIVE_ASSET_CODE = "XLM"
STROOPS_PER_XLM = 10_000_000

# Well-known asset issuers by network
# Allows simple symbols like "USDC" to auto-resolve to full Stellar assets
KNOWN_ASSET_ISSUERS = {
    "TESTNET": {
        "USDC": "GBBD47IF6LWK7P7MDEVSCWR7DPUWV3NY3DTQEVFL4NAT4AQH3ZLLFLA5",
    },
    "PUBLIC": {
        "USDC": "GA5ZSEJYB37JRC5AVCIA5MOP4RHTM335X2KGX3IHOJAPP5RE34K4KZVN",
        "yUSDC": "GDGTVWSM4MGS4T7Z6W4RPWOCHE2I6RDFCIFZGS3DOA63LWQTRNZNTTFF",
    },
}
