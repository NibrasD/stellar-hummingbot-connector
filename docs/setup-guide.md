# Setup Guide — Stellar DEX Connector for Hummingbot

## Prerequisites

### 1. Stellar Accounts

You need at minimum:
- **1 Master Account**: Your main trading account, funded with XLM and the assets you want to trade
- **2-5 Channel Accounts**: Funded with a small amount of XLM (minimum 2 XLM each for base reserve)

Channel accounts enable parallel transaction submission, preventing sequence number collisions.

#### Creating Channel Accounts

```python
from stellar_sdk import Keypair, Server, TransactionBuilder, Network, CreateAccount

# Generate keypairs
for i in range(3):
    kp = Keypair.random()
    print(f"Channel {i+1}: Secret={kp.secret}, Public={kp.public_key}")

# Fund each channel account from your master account
server = Server("https://horizon.stellar.org")
master = Keypair.from_secret("YOUR_MASTER_SECRET")
account = server.load_account(master.public_key)

for channel_public_key in channel_public_keys:
    tx = TransactionBuilder(
        source_account=account,
        network_passphrase=Network.PUBLIC_NETWORK_PASSPHRASE,
        base_fee=100,
    ).append_operation(
        CreateAccount(destination=channel_public_key, starting_balance="5")
    ).set_timeout(30).build()
    tx.sign(master)
    server.submit_transaction(tx)
```

### 2. Soroban RPC Access

Choose a Soroban RPC endpoint:

| Provider | URL | Notes |
|---|---|---|
| SDF Mainnet | `https://soroban-rpc.mainnet.stellar.gateway.fm` | Rate-limited |
| SDF Testnet | `https://soroban-testnet.stellar.org` | For testing |
| Ankr | `https://rpc.ankr.com/stellar_soroban` | Higher limits |
| QuickNode | Custom | Enterprise |

### 3. Python Environment

```bash
# Create a virtual environment
python -m venv hbot-stellar
source hbot-stellar/bin/activate  # or .\hbot-stellar\Scripts\activate on Windows

# Install Hummingbot
pip install hummingbot

# Install the Stellar connector
cd stellar-hummingbot-connector
pip install -e .
```

## Configuration

### Connecting in Hummingbot

```
>>> connect stellar

Enter your Soroban RPC URL: https://soroban-rpc.mainnet.stellar.gateway.fm
Enter your Stellar master account secret key: S...
Enter comma-separated channel account secret keys: SA...,SB...,SC...
Enter the network (PUBLIC or TESTNET): PUBLIC

Successfully connected to stellar.
```

### Running a Strategy

```
>>> start --script stellar_market_making_example.py
```

### Verifying Connection

```
>>> status
  Stellar DEX Connector Status
  ═══════════════════════════
  Network:    PUBLIC
  Connected:  True
  Channels:   3
  Account:    GABC12345678...

  Balances:
    XLM: 1000.00
    USDC: 500.00
```

## Troubleshooting

| Issue | Cause | Solution |
|---|---|---|
| `AccountNotFoundError` | Account not funded | Fund account with friendbot (testnet) or send XLM |
| `tx_bad_seq` errors | Sequence conflict | Increase channel accounts or reduce order frequency |
| `CONNECTION_ERROR` | RPC endpoint down | Try a different RPC provider |
| High fees | Network congestion | Increase `base_fee` in constants |
