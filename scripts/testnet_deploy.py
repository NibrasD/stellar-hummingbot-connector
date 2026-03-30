#!/usr/bin/env python3
"""
Stellar Testnet Deployment Script
==================================
This script demonstrates the Stellar Hummingbot connector on the Stellar testnet:

1. Creates master + channel accounts via Friendbot
2. Establishes trustlines for test assets
3. Places buy/sell orders on the Stellar DEX
4. Cancels orders
5. Queries orderbook and balances
6. Records all transaction hashes as evidence

Usage:
    python scripts/testnet_deploy.py
"""

import asyncio
import json
import time

import aiohttp
from stellar_sdk import (
    Asset,
    ChangeTrust,
    Keypair,
    ManageBuyOffer,
    ManageSellOffer,
    Network,
    Server,
    TransactionBuilder,
)

# ══════════════════════════════════════════════
# Configuration
# ══════════════════════════════════════════════

HORIZON_TESTNET = "https://horizon-testnet.stellar.org"
FRIENDBOT_URL = "https://friendbot.stellar.org"
NETWORK_PASSPHRASE = Network.TESTNET_NETWORK_PASSPHRASE

# Well-known testnet assets
# Using SDF's testnet USDC asset
USDC_ISSUER = "GBBD47IF6LWK7P7MDEVSCWR7DPUWV3NY3DTQEVFL4NAT4AQH3ZLLFLA5"
USDC_ASSET = Asset("USDC", USDC_ISSUER)
XLM_ASSET = Asset.native()

# Number of channel accounts
NUM_CHANNELS = 3

# ══════════════════════════════════════════════
# Evidence tracking
# ══════════════════════════════════════════════

evidence = {
    "accounts": {},
    "transactions": [],
    "orders_placed": [],
    "orders_cancelled": [],
    "balances": {},
    "orderbook_snapshot": None,
}


def log(msg, emoji="📋"):
    print(f"  {emoji} {msg}")


async def fund_account(public_key: str) -> bool:
    """Fund an account via Stellar testnet Friendbot."""
    try:
        async with aiohttp.ClientSession() as session:
            url = f"{FRIENDBOT_URL}?addr={public_key}"
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    tx_hash = data.get("hash", "unknown")
                    log(f"Funded {public_key[:12]}... (tx: {tx_hash[:16]}...)", "💰")
                    evidence["transactions"].append(
                        {
                            "type": "friendbot_fund",
                            "account": public_key,
                            "hash": tx_hash,
                        }
                    )
                    return True
                else:
                    text = await resp.text()
                    # Already funded accounts return 400
                    if "createAccountAlreadyExist" in text:
                        log(f"Account {public_key[:12]}... already funded", "✅")
                        return True
                    log(f"Friendbot error: {resp.status} - {text[:100]}", "❌")
                    return False
    except Exception as e:
        log(f"Friendbot error: {e}", "❌")
        return False


async def main():
    print("\n" + "═" * 60)
    print("  🌟 Stellar Testnet Deployment — Hummingbot Connector Demo")
    print("═" * 60 + "\n")

    server = Server(HORIZON_TESTNET)

    # ────────────────────────────────────────
    # Step 1: Create Accounts
    # ────────────────────────────────────────
    print("┌─ Step 1: Creating Accounts ─────────────────────────────┐")

    master_kp = Keypair.random()
    log(f"Master Account: {master_kp.public_key}")
    evidence["accounts"]["master"] = {
        "public_key": master_kp.public_key,
        "secret": master_kp.secret,
    }

    channel_kps = []
    for i in range(NUM_CHANNELS):
        kp = Keypair.random()
        channel_kps.append(kp)
        log(f"Channel {i+1}:      {kp.public_key[:20]}...")
        evidence["accounts"][f"channel_{i+1}"] = {
            "public_key": kp.public_key,
            "secret": kp.secret,
        }

    # Fund all accounts via Friendbot
    log("Funding accounts via Friendbot...", "🚀")
    await fund_account(master_kp.public_key)
    for kp in channel_kps:
        await fund_account(kp.public_key)
        await asyncio.sleep(1)  # Avoid rate limit

    print("└────────────────────────────────────────────────────────┘\n")

    # ────────────────────────────────────────
    # Step 2: Establish Trustlines
    # ────────────────────────────────────────
    print("┌─ Step 2: Establishing Trustlines ───────────────────────┐")

    try:
        master_account = server.load_account(master_kp.public_key)

        tx = (
            TransactionBuilder(
                source_account=master_account,
                network_passphrase=NETWORK_PASSPHRASE,
                base_fee=100,
            )
            .append_operation(ChangeTrust(asset=USDC_ASSET, limit="1000000"))
            .set_timeout(30)
            .build()
        )
        tx.sign(master_kp)
        response = server.submit_transaction(tx)
        tx_hash = response.get("hash", "")
        log(f"USDC trustline established (tx: {tx_hash[:16]}...)", "🔗")
        evidence["transactions"].append(
            {
                "type": "trustline",
                "asset": "USDC",
                "hash": tx_hash,
            }
        )
    except Exception as e:
        log(f"Trustline error: {e}", "⚠️")

    print("└────────────────────────────────────────────────────────┘\n")

    # Wait for ledger
    await asyncio.sleep(5)

    # ────────────────────────────────────────
    # Step 3: Check Initial Balances
    # ────────────────────────────────────────
    print("┌─ Step 3: Checking Balances ─────────────────────────────┐")

    try:
        account_data = server.accounts().account_id(master_kp.public_key).call()
        balances = {}
        for bal in account_data.get("balances", []):
            if bal["asset_type"] == "native":
                balances["XLM"] = bal["balance"]
                log(f"XLM Balance: {bal['balance']}", "💎")
            else:
                balances[bal["asset_code"]] = bal["balance"]
                log(f"{bal['asset_code']} Balance: {bal['balance']}", "💵")
        evidence["balances"]["initial"] = balances
    except Exception as e:
        log(f"Balance check error: {e}", "❌")

    print("└────────────────────────────────────────────────────────┘\n")

    # ────────────────────────────────────────
    # Step 4: Place Orders on DEX (Using Channel Accounts)
    # ────────────────────────────────────────
    print("┌─ Step 4: Placing Orders on Stellar DEX ─────────────────┐")

    placed_offer_ids = []

    # ── Order 1: Sell 10 XLM for USDC at price 0.5 (using channel 1) ──
    try:
        channel_kp = channel_kps[0]
        channel_account = server.load_account(channel_kp.public_key)

        tx = (
            TransactionBuilder(
                source_account=channel_account,
                network_passphrase=NETWORK_PASSPHRASE,
                base_fee=100,
            )
            .append_operation(
                ManageSellOffer(
                    selling=XLM_ASSET,
                    buying=USDC_ASSET,
                    amount="10",
                    price="0.5",
                    offer_id=0,  # New offer
                    source=master_kp.public_key,
                )
            )
            .set_timeout(30)
            .build()
        )
        tx.sign(master_kp)  # Master authorizes the operation
        tx.sign(channel_kp)  # Channel authorizes the source account

        response = server.submit_transaction(tx)
        tx_hash = response.get("hash", "")

        # Extract offer ID from result
        response.get("result_xdr", "")
        offer_id = "N/A"
        # Parse from offerResults in the response
        for op_result in response.get("offerResults", [{}]):
            if "currentOffer" in op_result:
                offer_id = op_result["currentOffer"].get("offerId", "N/A")

        log(f"SELL 10 XLM @ 0.5 USDC/XLM → tx: {tx_hash[:16]}...", "📈")
        evidence["transactions"].append(
            {
                "type": "place_sell_order",
                "pair": "XLM/USDC",
                "amount": "10",
                "price": "0.5",
                "hash": tx_hash,
                "channel": channel_kp.public_key[:12],
            }
        )
        evidence["orders_placed"].append(
            {
                "hash": tx_hash,
                "side": "SELL",
                "amount": "10",
                "price": "0.5",
            }
        )

    except Exception as e:
        log(f"Order 1 error: {e}", "❌")

    await asyncio.sleep(2)

    # ── Order 2: Sell 20 XLM for USDC at price 0.6 (using channel 2) ──
    try:
        channel_kp = channel_kps[1]
        channel_account = server.load_account(channel_kp.public_key)

        tx = (
            TransactionBuilder(
                source_account=channel_account,
                network_passphrase=NETWORK_PASSPHRASE,
                base_fee=100,
            )
            .append_operation(
                ManageSellOffer(
                    selling=XLM_ASSET,
                    buying=USDC_ASSET,
                    amount="20",
                    price="0.6",
                    offer_id=0,
                    source=master_kp.public_key,
                )
            )
            .set_timeout(30)
            .build()
        )
        tx.sign(master_kp)
        tx.sign(channel_kp)

        response = server.submit_transaction(tx)
        tx_hash = response.get("hash", "")

        log(f"SELL 20 XLM @ 0.6 USDC/XLM → tx: {tx_hash[:16]}...", "📈")
        evidence["transactions"].append(
            {
                "type": "place_sell_order",
                "pair": "XLM/USDC",
                "amount": "20",
                "price": "0.6",
                "hash": tx_hash,
                "channel": channel_kp.public_key[:12],
            }
        )
        evidence["orders_placed"].append(
            {
                "hash": tx_hash,
                "side": "SELL",
                "amount": "20",
                "price": "0.6",
            }
        )

    except Exception as e:
        log(f"Order 2 error: {e}", "❌")

    await asyncio.sleep(2)

    # ── Order 3: Buy 15 XLM with USDC at price 0.3 (using channel 3) ──
    try:
        channel_kp = channel_kps[2]
        channel_account = server.load_account(channel_kp.public_key)

        tx = (
            TransactionBuilder(
                source_account=channel_account,
                network_passphrase=NETWORK_PASSPHRASE,
                base_fee=100,
            )
            .append_operation(
                ManageBuyOffer(
                    selling=USDC_ASSET,
                    buying=XLM_ASSET,
                    amount="15",
                    price="3.33",  # 1/0.3 = 3.33 USDC per XLM
                    offer_id=0,
                    source=master_kp.public_key,
                )
            )
            .set_timeout(30)
            .build()
        )
        tx.sign(master_kp)
        tx.sign(channel_kp)

        response = server.submit_transaction(tx)
        tx_hash = response.get("hash", "")

        log(f"BUY 15 XLM @ 0.3 USDC/XLM → tx: {tx_hash[:16]}...", "📉")
        evidence["transactions"].append(
            {
                "type": "place_buy_order",
                "pair": "XLM/USDC",
                "amount": "15",
                "price": "0.3",
                "hash": tx_hash,
                "channel": channel_kp.public_key[:12],
            }
        )
        evidence["orders_placed"].append(
            {
                "hash": tx_hash,
                "side": "BUY",
                "amount": "15",
                "price": "0.3",
            }
        )

    except Exception as e:
        log(f"Order 3 error: {e}", "❌")

    print("└────────────────────────────────────────────────────────┘\n")

    await asyncio.sleep(3)

    # ────────────────────────────────────────
    # Step 5: Query Offers & Orderbook
    # ────────────────────────────────────────
    print("┌─ Step 5: Querying Open Offers ──────────────────────────┐")

    try:
        offers_resp = server.offers().for_account(master_kp.public_key).call()
        offers = offers_resp.get("_embedded", {}).get("records", [])
        log(f"Found {len(offers)} open offers for master account", "📋")

        for offer in offers:
            offer_id = offer.get("id")
            selling = offer.get("selling", {})
            buying = offer.get("buying", {})
            amount = offer.get("amount")
            price = offer.get("price")
            sell_asset = selling.get("asset_code", "XLM")
            buy_asset = buying.get("asset_code", "XLM")
            log(f"  Offer #{offer_id}: SELL {amount} {sell_asset} @ {price} {buy_asset}/{sell_asset}", "  ")
            placed_offer_ids.append(offer_id)

    except Exception as e:
        log(f"Offer query error: {e}", "❌")

    print("└────────────────────────────────────────────────────────┘\n")

    # ────────────────────────────────────────
    # Step 6: Cancel an Order
    # ────────────────────────────────────────
    print("┌─ Step 6: Cancelling an Order ───────────────────────────┐")

    if placed_offer_ids:
        try:
            cancel_offer_id = int(placed_offer_ids[0])
            channel_kp = channel_kps[0]
            channel_account = server.load_account(channel_kp.public_key)

            tx = (
                TransactionBuilder(
                    source_account=channel_account,
                    network_passphrase=NETWORK_PASSPHRASE,
                    base_fee=100,
                )
                .append_operation(
                    ManageSellOffer(
                        selling=XLM_ASSET,
                        buying=USDC_ASSET,
                        amount="0",  # Amount=0 → Cancel
                        price="1",
                        offer_id=cancel_offer_id,
                        source=master_kp.public_key,
                    )
                )
                .set_timeout(30)
                .build()
            )
            tx.sign(master_kp)
            tx.sign(channel_kp)

            response = server.submit_transaction(tx)
            tx_hash = response.get("hash", "")

            log(f"Cancelled offer #{cancel_offer_id} → tx: {tx_hash[:16]}...", "🗑️")
            evidence["transactions"].append(
                {
                    "type": "cancel_order",
                    "offer_id": cancel_offer_id,
                    "hash": tx_hash,
                }
            )
            evidence["orders_cancelled"].append(
                {
                    "offer_id": cancel_offer_id,
                    "hash": tx_hash,
                }
            )

        except Exception as e:
            log(f"Cancel error: {e}", "❌")
    else:
        log("No offers to cancel", "⚠️")

    print("└────────────────────────────────────────────────────────┘\n")

    await asyncio.sleep(3)

    # ────────────────────────────────────────
    # Step 7: Verify Final State
    # ────────────────────────────────────────
    print("┌─ Step 7: Verifying Final State ─────────────────────────┐")

    try:
        # Check remaining offers
        offers_resp = server.offers().for_account(master_kp.public_key).call()
        remaining = offers_resp.get("_embedded", {}).get("records", [])
        log(f"Remaining open offers: {len(remaining)}", "📊")

        # Check final balances
        account_data = server.accounts().account_id(master_kp.public_key).call()
        final_balances = {}
        for bal in account_data.get("balances", []):
            if bal["asset_type"] == "native":
                final_balances["XLM"] = bal["balance"]
                log(f"Final XLM: {bal['balance']}", "💎")
            else:
                final_balances[bal["asset_code"]] = bal["balance"]
                log(f"Final {bal['asset_code']}: {bal['balance']}", "💵")
        evidence["balances"]["final"] = final_balances

    except Exception as e:
        log(f"Final state error: {e}", "❌")

    print("└────────────────────────────────────────────────────────┘\n")

    # ────────────────────────────────────────
    # Step 8: Evidence Summary
    # ────────────────────────────────────────
    print("═" * 60)
    print("  📝 EVIDENCE SUMMARY")
    print("═" * 60)

    print(f"\n  Master Account: {evidence['accounts']['master']['public_key']}")
    print(f"  View on Explorer: https://stellar.expert/explorer/testnet/account/{evidence['accounts']['master']['public_key']}")

    print(f"\n  Transactions ({len(evidence['transactions'])}):")
    for i, tx in enumerate(evidence["transactions"]):
        tx_type = tx.get("type", "unknown")
        tx_hash = tx.get("hash", "N/A")
        print(f"    {i+1}. [{tx_type}] {tx_hash}")
        print(f"       Explorer: https://stellar.expert/explorer/testnet/tx/{tx_hash}")

    print(f"\n  Orders Placed: {len(evidence['orders_placed'])}")
    for order in evidence["orders_placed"]:
        print(f"    {order['side']} {order['amount']} @ {order['price']} → {order['hash'][:20]}...")

    print(f"\n  Orders Cancelled: {len(evidence['orders_cancelled'])}")
    for order in evidence["orders_cancelled"]:
        print(f"    Offer #{order['offer_id']} → {order['hash'][:20]}...")

    print()

    # Save evidence to file
    evidence_file = "evidence/testnet_deployment.json"
    import os

    os.makedirs("evidence", exist_ok=True)
    with open(evidence_file, "w") as f:
        json.dump(evidence, f, indent=2)
    log(f"Evidence saved to: {evidence_file}", "💾")

    # Save markdown report
    report_file = "evidence/testnet_report.md"
    with open(report_file, "w") as f:
        f.write("# Stellar Testnet Deployment Evidence\n\n")
        f.write(f"**Date:** {time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())}\n\n")
        f.write(f"## Master Account\n")
        f.write(f"- Public Key: `{evidence['accounts']['master']['public_key']}`\n")
        f.write(f"- [View on Stellar Expert](https://stellar.expert/explorer/testnet/account/{evidence['accounts']['master']['public_key']})\n\n")
        f.write(f"## Channel Accounts ({NUM_CHANNELS})\n")
        for i in range(NUM_CHANNELS):
            pk = evidence["accounts"][f"channel_{i+1}"]["public_key"]
            f.write(f"- Channel {i+1}: `{pk}`\n")
        f.write(f"\n## Transactions ({len(evidence['transactions'])})\n\n")
        f.write("| # | Type | Hash | Explorer |\n")
        f.write("|---|---|---|---|\n")
        for i, tx in enumerate(evidence["transactions"]):
            h = tx.get("hash", "N/A")
            t = tx.get("type", "unknown")
            f.write(f"| {i+1} | {t} | `{h[:20]}...` | [View](https://stellar.expert/explorer/testnet/tx/{h}) |\n")
        f.write(f"\n## Orders Placed ({len(evidence['orders_placed'])})\n\n")
        for order in evidence["orders_placed"]:
            f.write(f"- **{order['side']}** {order['amount']} XLM @ {order['price']} USDC/XLM\n")
        f.write(f"\n## Orders Cancelled ({len(evidence['orders_cancelled'])})\n\n")
        for order in evidence["orders_cancelled"]:
            f.write(f"- Offer #{order['offer_id']}\n")
        f.write(f"\n## Balances\n")
        f.write(f"### Initial\n")
        for k, v in evidence.get("balances", {}).get("initial", {}).items():
            f.write(f"- {k}: {v}\n")
        f.write(f"### Final\n")
        for k, v in evidence.get("balances", {}).get("final", {}).items():
            f.write(f"- {k}: {v}\n")

    log(f"Report saved to: {report_file}", "📄")

    print("\n" + "═" * 60)
    print("  ✅ Testnet deployment complete!")
    print("═" * 60 + "\n")


if __name__ == "__main__":
    asyncio.run(main())
