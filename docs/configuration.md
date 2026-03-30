# Configuration Reference — Stellar DEX Connector

## Connection Parameters

| Parameter | Type | Default | Description |
|---|---|---|---|
| `stellar_rpc_url` | string | `https://soroban-rpc.mainnet.stellar.gateway.fm` | Soroban RPC endpoint URL |
| `stellar_master_secret` | secret | *required* | Master trading account secret key |
| `stellar_channel_secrets` | string | `""` | Comma-separated channel account secrets |
| `stellar_network` | string | `PUBLIC` | Network: `PUBLIC` or `TESTNET` |

## Constants (stellar_constants.py)

### Transaction Settings

| Constant | Default | Description |
|---|---|---|
| `DEFAULT_BASE_FEE` | `100` | Base fee in stroops (0.00001 XLM) |
| `MAX_BASE_FEE` | `10000` | Maximum fee for fee bumping |
| `TRANSACTION_TIMEOUT_SECONDS` | `30` | Transaction validity window |
| `TRANSACTION_POLL_INTERVAL` | `2.0` | Seconds between status polls |
| `TRANSACTION_MAX_RETRIES` | `15` | Max poll attempts |

### Polling Intervals

| Constant | Default | Description |
|---|---|---|
| `ORDER_BOOK_POLL_INTERVAL` | `3.0` | Orderbook refresh interval |
| `TRADE_POLL_INTERVAL` | `3.0` | Trade listener polling interval |
| `BALANCE_POLL_INTERVAL` | `10.0` | Balance check interval |
| `USER_STREAM_POLL_INTERVAL` | `2.0` | User stream update interval |

### Rate Limits

| Limit | Value | Description |
|---|---|---|
| `stellar_rpc` | 30/second | RPC call limit |
| `stellar_general` | 10/second | General request limit |

## Market Making Strategy Parameters

| Parameter | Type | Default | Description |
|---|---|---|---|
| `trading_pair` | string | *required* | Trading pair (e.g., `USDC-GA5Z...-XLM`) |
| `bid_spread` | Decimal | `0.01` | Bid spread from mid price (1%) |
| `ask_spread` | Decimal | `0.01` | Ask spread from mid price (1%) |
| `order_amount` | Decimal | `10` | Amount per order |
| `order_refresh_time` | float | `30.0` | Seconds between order refreshes |
| `order_levels` | int | `1` | Number of order levels per side |
| `order_level_spread` | Decimal | `0.005` | Additional spread per level |
| `inventory_skew_enabled` | bool | `False` | Enable inventory balancing |

## AMM Arbitrage Strategy Parameters

| Parameter | Type | Default | Description |
|---|---|---|---|
| `min_profitability` | Decimal | `0.003` | Minimum profit threshold (0.3%) |
| `order_amount` | Decimal | `10` | Amount per arbitrage trade |
| `poll_interval` | float | `5.0` | Seconds between price checks |
| `slippage_buffer` | Decimal | `0.001` | Slippage protection (0.1%) |
| `network_fee_xlm` | Decimal | `0.00002` | Estimated fee per side |

## Trading Pair Format

```
# Native asset
XLM

# Issued asset
USDC-GA5ZSEJYB37JRC5AVCIA5MOP4RHTM335X2KGX3IHOJAPP5RE34K4KZVN

# Trading pair: base-quote
USDC-GA5ZSEJYB37JRC5AVCIA5MOP4RHTM335X2KGX3IHOJAPP5RE34K4KZVN-XLM
```
