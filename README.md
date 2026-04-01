# Stellar DEX Connector for Hummingbot

<div align="center">
  <h3>🌟 Algorithmic Trading on the Stellar Decentralized Exchange</h3>
  <p>A production-ready connector enabling market-making, arbitrage, and automated trading strategies on Stellar DEX through the Hummingbot framework.</p>
</div>

---

## Overview

This connector integrates the **Stellar Decentralized Exchange (DEX)** with [Hummingbot](https://hummingbot.org), the leading open-source algorithmic trading framework. It fills the gap left by the deprecation of Kelp and other community market-making tools.

### Key Features

| Feature | Description |
|---|---|
| **Stellar RPC First** | Uses Stellar RPC for network interactions |
| **Channel Accounts** | Parallel transaction submission via configurable channel account pool |
| **Full Order Lifecycle** | Submit, cancel, track, partial fill detection |
| **Transaction Pipeline** | Queued, retry-aware transaction processing with sequence conflict handling |
| **Market Making** | Built-in market making strategy with multi-level orders and inventory skew |
| **AMM Arbitrage** | Intra-Soroban AMM and cross-venue arbitrage strategy |
| **Any Trading Pair** | Supports native XLM and any issued asset on the Stellar network |
| **XRPL Reference** | Architecture follows the official XRPL connector pattern |

## Architecture

```
hummingbot/connector/exchange/stellar/
├── stellar_exchange.py              # Main connector (ExchangePyBase)
├── stellar_auth.py                  # Channel accounts & tx signing
├── stellar_client.py                # Soroban RPC client
├── stellar_api_order_book_data_source.py  # Orderbook streaming
├── stellar_api_user_stream_data_source.py # User balance/order stream
├── stellar_fill_processor.py        # Trade fill matching
├── stellar_order_placement_strategy.py    # Smart order placement
├── stellar_transaction_pipeline.py  # Tx queuing & retry
├── stellar_worker_manager.py        # Background task coordination
├── stellar_worker_pool.py           # Async worker pool
├── stellar_order_book.py            # OrderBook messages
├── stellar_xdr_utils.py             # XDR construction & parsing
├── stellar_web_utils.py             # HTTP/RPC utilities
├── stellar_utils.py                 # Config model & helpers
├── stellar_constants.py             # Constants & rate limits
├── dummy.pxd / dummy.pyx           # Cython build stubs
```

## Quick Start

### Prerequisites

- Python 3.10+
- Hummingbot installed
- A funded Stellar account (master)
- 2-5 funded channel accounts (recommended)
- Access to a Soroban RPC endpoint

### Installation

```bash
# Clone this repository
git clone https://github.com/your-org/stellar-hummingbot-connector.git

# Install in your Hummingbot environment
cd stellar-hummingbot-connector
pip install -e .
```

### Configuration

In Hummingbot, run `connect stellar` and provide:

| Parameter | Description | Example |
|---|---|---|
| `stellar_rpc_url` | Soroban RPC endpoint | `https://soroban-rpc.mainnet.stellar.gateway.fm` |
| `stellar_master_secret` | Master account secret key | `SXXXXXXXXXXX...` |
| `stellar_channel_secrets` | Comma-separated channel secrets | `SA...,SB...,SC...` |
| `stellar_network` | Network selection | `PUBLIC` or `TESTNET` |

### Running a Market Making Bot

```bash
# In Hummingbot
start --script stellar_market_making_example.py
```

## Strategies

### 1. Market Making (`stellar_market_maker`)
Places bid and ask orders around the mid-price with configurable spreads. Supports:
- Multi-level order placement
- Inventory-based skew
- Automatic order refresh
- Atomic cancel-and-replace

### 2. AMM Arbitrage (`stellar_amm_arbitrage`)
Monitors price discrepancies between venues and executes when profitable:
- Stellar DEX vs Soroban AMMs (Soroswap, Aquarius)
- Intra-Soroban AMM arbitrage
- Cross-venue arbitrage with external CEXs

## Testing

```bash
# Run all tests
pytest tests/ -v

# Run with coverage
pytest tests/ --cov=hummingbot/connector/exchange/stellar --cov-report=html
```

## Documentation

- [Setup Guide](docs/setup-guide.md)
- [Configuration Reference](docs/configuration.md)
- [Strategy Examples](docs/strategies.md)
- [AMM Support](docs/amm-support.md)
- [Architecture Overview](docs/stellar-connector.md)

## License

Apache 2.0 — See [LICENSE](LICENSE) for details.
