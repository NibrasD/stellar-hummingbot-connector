# AMM Support — Stellar DEX Connector

## Overview

The Stellar connector includes foundational support for Automated Market Makers (AMMs),
both classic Stellar liquidity pools and Soroban-based smart contract AMMs.

## Architecture

```
┌──────────────────────────────────────────┐
│         Stellar DEX Connector            │
├──────────────┬───────────────────────────┤
│  Classic DEX │  Soroban AMMs             │
│  Orderbook   │  ┌─────────┐ ┌─────────┐ │
│  (Horizon)   │  │Soroswap │ │Aquarius │ │
│              │  └─────────┘ └─────────┘ │
├──────────────┤  Classic LPs              │
│   Soroban    │  ┌─────────────────────┐  │
│   RPC        │  │  Stellar AMM Pools  │  │
│              │  └─────────────────────┘  │
└──────────────┴───────────────────────────┘
```

## Classic Stellar Liquidity Pools

Stellar's built-in liquidity pools (Protocol 18+) enable constant-product AMMs
at the protocol level.

### Supported Operations
- **Depositing** liquidity into classic pools
- **Withdrawing** liquidity from classic pools
- **Path payments** that route through classic pools
- **Pool share balance tracking** via trustlines

### Usage
Classic liquidity pools are automatically included in Horizon's orderbook queries,
so the connector's orderbook data source already includes pool-sourced liquidity.

## Soroban AMM Integration

### Soroswap
[Soroswap](https://soroswap.finance) is a Uniswap-style AMM built on Soroban.

**Contract Interaction Pattern:**
```python
# Quote a swap on Soroswap
from stellar_sdk import SorobanServer, TransactionBuilder

# 1. Build a contract invocation
invoke_op = InvokeHostFunction(
    function=AuthorizedFunction.CONTRACT_FN,
    contract_id=SOROSWAP_ROUTER_CONTRACT,
    function_name="swap_exact_tokens_for_tokens",
    args=[amount_in, amount_out_min, path, to, deadline],
)

# 2. Simulate to get resource footprint
simulation = await client.simulate_transaction(tx_xdr)

# 3. Submit the transaction (after adding simulation results)
result = await client.submit_and_wait(prepared_tx_xdr)
```

### Aquarius
[Aquarius](https://aqua.network) provides AMM pools with unique reward mechanisms.

### Event Monitoring
The connector uses Soroban RPC `getEvents` to monitor AMM contract events:

```python
# Fetch swap events from Soroswap
events = await client.get_events(
    start_ledger=last_processed_ledger,
    event_type="contract",
    contract_ids=[SOROSWAP_ROUTER_CONTRACT],
    topics=[["AAAADwAAAARzd2Fw"]],  # "swap" topic in SCVal
)
```

## Intra-Soroban AMM Arbitrage

The `stellar_amm_arbitrage` strategy exploits price differences between:

1. **Soroswap vs Aquarius**: Different AMM implementations with different pool depths
2. **AMM vs Classic DEX**: Soroban AMM prices vs traditional orderbook
3. **AMM vs Classic LP**: Soroban AMM vs protocol-level liquidity pools

### How It Works

```
Pool A (Soroswap):  1 XLM = 0.098 USDC
Pool B (Aquarius):  1 XLM = 0.102 USDC

→ Buy 1000 XLM on Soroswap @ 0.098
→ Sell 1000 XLM on Aquarius @ 0.102
→ Profit: 4 USDC (minus fees)
```

### Configuration

```python
strategy = StellarAmmArbitrage(
    exchange_1=soroswap_connector,
    exchange_2=aquarius_connector,
    trading_pair="XLM-USDC",
    min_profitability=Decimal("0.003"),
    order_amount=Decimal("1000"),
)
```

## Future Roadmap

- [ ] Direct Soroban contract invocation for swaps (bypass orderbook)
- [ ] Flash loan-style atomic arbitrage within a single Soroban transaction
- [ ] Liquidity provision strategy for Soroban AMMs
- [ ] Pool analytics and optimal rebalancing
- [ ] MEV protection via private Soroban transaction submission
