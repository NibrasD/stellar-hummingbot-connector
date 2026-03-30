# Trading Strategies — Stellar DEX Connector

## 1. Market Making Strategy

### Overview
The market making strategy places buy and sell orders around the current mid-price, earning the spread on each completed round-trip.

### How It Works

```
                   ASK (0.1050)  ← Your sell order
                   ────────────
        Mid Price: 0.1000
                   ────────────
                   BID (0.0950)  ← Your buy order
```

1. Fetch the current orderbook mid-price
2. Place a BID at `mid_price × (1 - bid_spread)`
3. Place an ASK at `mid_price × (1 + ask_spread)`
4. When both sides fill, you earn the spread
5. Refresh orders every `order_refresh_time` seconds

### Configuration Example

```python
# scripts/stellar_market_making_example.py
exchange = "stellar"
trading_pair = "USDC-GA5Z...-XLM"
order_amount = Decimal("100")      # 100 units per side
bid_spread = Decimal("0.005")      # 0.5% below mid
ask_spread = Decimal("0.005")      # 0.5% above mid
order_refresh_time = 30            # Refresh every 30s
```

### Multi-Level Orders
Place multiple orders at different price levels for deeper liquidity:

```python
order_levels = 3
order_level_spread = Decimal("0.005")  # 0.5% additional per level
```

This creates:
- Level 0: BID -0.5% / ASK +0.5%
- Level 1: BID -1.0% / ASK +1.0%
- Level 2: BID -1.5% / ASK +1.5%

### Inventory Skew
Automatically adjust order sizes based on your inventory position:

```python
inventory_skew_enabled = True
inventory_target_base_pct = Decimal("0.5")  # Target 50% in base asset
```

---

## 2. AMM Arbitrage Strategy

### Overview
The arbitrage strategy monitors price differences between two venues and executes trades when the discrepancy exceeds the minimum profitability threshold.

### Supported Venue Combinations

| Exchange 1 | Exchange 2 | Description |
|---|---|---|
| Stellar DEX | Binance | Cross-venue CEX/DEX arbitrage |
| Stellar DEX | Soroswap AMM | DEX vs Soroban AMM |
| Soroswap | Aquarius | Intra-Soroban AMM arbitrage |
| Stellar DEX | Classic LP | DEX vs classic liquidity pools |

### How It Works

```
1. Check prices on both venues:
   Venue A: Best Ask = 0.0990 (you can buy at)
   Venue B: Best Bid = 0.1020 (you can sell at)

2. Calculate net profit:
   Gross: (0.1020 - 0.0990) / 0.0990 = 3.03%
   Fees:  2 × 0.00002 XLM ≈ negligible
   Net:   ~3.0%

3. If net > min_profitability (0.3%):
   → Buy 500 XLM on Venue A @ 0.0990
   → Sell 500 XLM on Venue B @ 0.1020
   → Profit: ~1.5 USDC
```

### Configuration Example

```python
# scripts/stellar_arbitrage_example.py
stellar_exchange = "stellar"
other_exchange = "binance"
min_profitability = Decimal("0.003")   # 0.3% minimum
order_amount = Decimal("500")
slippage_buffer = Decimal("0.001")     # 0.1% slippage protection
```

---

## 3. Running Strategies

### Via Script

```bash
# In Hummingbot
start --script stellar_market_making_example.py
```

### Via Strategy Config

```bash
# In Hummingbot
create
# Select "stellar_market_maker" or "stellar_amm_arbitrage"
# Fill in parameters
start
```

### Monitoring

```bash
status          # View current strategy status
history         # View trade history
open_orders     # View active orders
```
