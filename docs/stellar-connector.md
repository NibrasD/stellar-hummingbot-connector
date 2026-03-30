# Stellar DEX Connector — Architecture Overview

## 1. Background & Motivation

The deprecation of previous community market-making tools, such as Kelp, has created a significant gap in the ecosystem's tooling. This connector fills that gap by integrating Stellar DEX support into Hummingbot, the leading open-source Python framework for automated trading.

### Key Outcomes
- **Increased Liquidity:** Easy, low-cost professional market-making for companies and community members
- **Improved Price Accuracy:** Efficient arbitrage between Stellar DEX and other exchanges
- **Lower Barrier to Entry:** Leverages Hummingbot's maintenance team and existing user base

## 2. Architecture

### Component Overview

```
┌─────────────────────────────────────────────────────────┐
│                    StellarExchange                       │
│                  (ExchangePyBase)                        │
├─────────────┬────────────────┬──────────────────────────┤
│  Order      │  Data Sources  │  Infrastructure          │
│  Management │                │                          │
│             │                │                          │
│ Placement   │ OrderBook      │ TransactionPipeline      │
│ Strategy    │ DataSource     │   ├─ Worker Pool         │
│             │                │   ├─ Worker Manager      │
│ Fill        │ UserStream     │   └─ Retry Logic         │
│ Processor   │ DataSource     │                          │
├─────────────┴────────────────┤ StellarAuth              │
│        StellarClient         │   ├─ Channel Accounts    │
│  (Soroban RPC + Horizon)     │   └─ TX Signing          │
└──────────────────────────────┴──────────────────────────┘
│                    Stellar Network                       │
│  ┌─────────────┐  ┌──────────┐  ┌────────────────────┐  │
│  │ Soroban RPC │  │ Horizon  │  │ Soroban Contracts  │  │
│  │ (Primary)   │  │(Fallback)│  │ (AMMs)             │  │
│  └─────────────┘  └──────────┘  └────────────────────┘  │
└─────────────────────────────────────────────────────────┘
```

### RPC vs Horizon Usage

| Operation | Protocol | Justification |
|---|---|---|
| Transaction submission | **Soroban RPC** | `sendTransaction` — primary |
| Transaction status | **Soroban RPC** | `getTransaction` — primary |
| Account data | **Soroban RPC** | `getLedgerEntries` with account keys |
| Trustline balances | **Soroban RPC** | `getLedgerEntries` with trustline keys |
| Offer status | **Soroban RPC** | `getLedgerEntries` with offer keys |
| Sequence numbers | **Soroban RPC** | Extracted from account entry |
| DEX Orderbook | **Horizon** | RPC lacks native orderbook aggregation |
| Trade history | **Horizon** | RPC lacks DEX trade queries |
| Soroban events | **Soroban RPC** | `getEvents` for AMM monitoring |

### Channel Accounts Flow

```
1. Strategy requests order placement
2. Pipeline acquires channel account from pool
3. Transaction built with channel as source, master as op source
4. Signed by both master key and channel key
5. Submitted via Soroban RPC sendTransaction
6. Poll getTransaction for confirmation
7. Channel account released back to pool
8. Result callback invoked with fill data
```

## 3. Requirements Mapping

### Core Exchange Support ✅
- **Order Management:** `StellarOrderPlacementStrategy` + `StellarTransactionPipeline` handle submit/cancel
- **Local Orderbook:** `StellarAPIOrderBookDataSource` maintains real-time copy
- **Trade Listening:** Continuous polling with cursor-based pagination
- **Parallel Transactions:** `StellarAuth` channel account pool with `StellarWorkerPool`
- **Account Balance:** Via `getLedgerEntries` RPC (not Horizon)
- **Any Trading Pair:** `stellar_utils.py` parses any `CODE-ISSUER` format
- **RPC Protocol:** Soroban RPC is the primary protocol for all operations

### Advanced AMM Support (Optional) ✅
- **Classic Liquidity Pools:** Liquidity automatically included in orderbook queries
- **Soroban AMMs:** Architecture supports `getEvents` monitoring of Soroswap/Aquarius
- **Intra-Soroban Arbitrage:** Dedicated `StellarAmmArbitrage` strategy

## 4. Deliverables Status

- [x] **Connector Development:** Full connector with 16 source files
- [x] **Stellar DEX Orderbook Support:** Direct interaction enabled
- [x] **Official Integration:** XRPL-pattern structure, KEYS config, Cython stubs
- [x] **Documentation & Examples:** 5 doc files, 2 example scripts, comprehensive README
- [ ] **Mainnet Transactions & Video:** Pending final deployment
- [x] **Test Suite:** 45+ unit tests across 6 test files
- [x] **AMM Support:** Architecture + strategy for Soroban AMM arbitrage

## 5. File Index

| File | LOC | Purpose |
|---|---|---|
| `stellar_exchange.py` | ~380 | Main connector class |
| `stellar_client.py` | ~310 | Soroban RPC client |
| `stellar_auth.py` | ~170 | Channel account management |
| `stellar_transaction_pipeline.py` | ~230 | Transaction lifecycle |
| `stellar_order_placement_strategy.py` | ~220 | Smart order placement |
| `stellar_fill_processor.py` | ~200 | Trade fill matching |
| `stellar_api_order_book_data_source.py` | ~180 | Orderbook streaming |
| `stellar_api_user_stream_data_source.py` | ~160 | User data stream |
| `stellar_xdr_utils.py` | ~300 | XDR construction/parsing |
| `stellar_web_utils.py` | ~130 | HTTP/RPC utilities |
| `stellar_worker_pool.py` | ~100 | Async worker pool |
| `stellar_worker_manager.py` | ~100 | Worker coordination |
| `stellar_order_book.py` | ~60 | OrderBook messages |
| `stellar_utils.py` | ~160 | Config model + helpers |
| `stellar_constants.py` | ~90 | Constants & rate limits |
| **Total** | **~2,790** | |
