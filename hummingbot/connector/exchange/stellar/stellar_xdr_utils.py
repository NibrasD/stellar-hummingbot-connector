# hummingbot/connector/exchange/stellar/stellar_xdr_utils.py
"""
XDR construction and parsing utilities for Stellar DEX operations.
Handles ManageOffer operations, transaction result decoding, and ledger entry parsing.

Compatible with stellar-sdk v13.x
"""

import base64
import logging
from decimal import Decimal
from typing import Any, Dict, Optional

from stellar_sdk import Asset, Keypair
from stellar_sdk.xdr import (
    AccountEntry,
    AccountID,
    AssetType,
    Int64,
    LedgerEntryData,
    LedgerEntryType,
    LedgerKey,
    LedgerKeyAccount,
    LedgerKeyOffer,
    LedgerKeyTrustLine,
    OfferEntry,
    PublicKey,
    PublicKeyType,
    TransactionResult,
    TransactionResultCode,
    TrustLineAsset,
    TrustLineEntry,
    Uint256,
)

from .stellar_constants import STROOPS_PER_XLM

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
# ManageOffer Operation Builders
# ──────────────────────────────────────────────


def build_manage_sell_offer_op(
    selling: Asset,
    buying: Asset,
    amount: str,
    price: str,
    offer_id: int = 0,
    source: str = None,
):
    """
    Builds a ManageSellOfferOp for the Stellar DEX.

    Args:
        selling: The asset being sold.
        buying: The asset being bought.
        amount: The amount of the selling asset to offer (set to "0" to cancel).
        price: The price in terms of buying/selling.
        offer_id: The offer ID to modify (0 = create new).
        source: Optional source account public key.

    Returns:
        A ManageSellOffer operation object.
    """
    from stellar_sdk import ManageSellOffer

    op = ManageSellOffer(
        selling=selling,
        buying=buying,
        amount=amount,
        price=price,
        offer_id=offer_id,
        source=source,
    )
    return op


def build_manage_buy_offer_op(
    selling: Asset,
    buying: Asset,
    amount: str,
    price: str,
    offer_id: int = 0,
    source: str = None,
):
    """
    Builds a ManageBuyOfferOp for the Stellar DEX.
    """
    from stellar_sdk import ManageBuyOffer

    op = ManageBuyOffer(
        selling=selling,
        buying=buying,
        amount=amount,
        price=price,
        offer_id=offer_id,
        source=source,
    )
    return op


def build_cancel_offer_op(
    selling: Asset,
    buying: Asset,
    offer_id: int,
    source: str = None,
):
    """
    Builds a ManageSellOfferOp that cancels an existing offer (amount=0).
    """
    return build_manage_sell_offer_op(
        selling=selling,
        buying=buying,
        amount="0",
        price="1",  # Price doesn't matter for cancellation
        offer_id=offer_id,
        source=source,
    )


# ──────────────────────────────────────────────
# Transaction Result Decoding
# ──────────────────────────────────────────────


def decode_transaction_result(result_xdr: str) -> Dict[str, Any]:
    """
    Decodes a TransactionResult XDR string to extract success status and offer details.

    Args:
        result_xdr: Base64-encoded TransactionResult XDR.

    Returns:
        Dictionary with:
        - success (bool): Whether the transaction was successful
        - offer_id (int|None): The offer ID if a manage offer operation was processed
        - offers_claimed (list): List of claimed offers (partial/full fills)
        - fee_charged (int): The fee charged in stroops
    """
    try:
        xdr_bytes = base64.b64decode(result_xdr)
        tx_result = TransactionResult.from_xdr_bytes(xdr_bytes)

        fee_charged = tx_result.fee_charged.int64 if tx_result.fee_charged else 0
        success = tx_result.result.code == TransactionResultCode.txSUCCESS

        offer_id = None
        offers_claimed = []

        if success and tx_result.result.results:
            for op_result in tx_result.result.results:
                if op_result.tr is None:
                    continue

                # Handle ManageSellOffer results
                manage_result = None
                if hasattr(op_result.tr, "manage_sell_offer_result") and op_result.tr.manage_sell_offer_result:
                    manage_result = op_result.tr.manage_sell_offer_result
                elif hasattr(op_result.tr, "manage_buy_offer_result") and op_result.tr.manage_buy_offer_result:
                    manage_result = op_result.tr.manage_buy_offer_result

                if manage_result and manage_result.success:
                    result_offer = manage_result.success.offer
                    if result_offer and hasattr(result_offer, "offer") and result_offer.offer:
                        offer_id = result_offer.offer.offer_id.int64

                    # Extract claimed offers (fills)
                    claimed = manage_result.success.offers_claimed or []
                    for claim in claimed:
                        if hasattr(claim, "v0"):
                            c = claim.v0
                        else:
                            c = claim
                        offers_claimed.append(
                            {
                                "seller_id": c.seller_id.account_id.ed25519.uint256.hex() if hasattr(c, "seller_id") else None,
                                "offer_id": c.offer_id.int64 if hasattr(c, "offer_id") else None,
                                "amount_sold": c.amount_sold.int64 / STROOPS_PER_XLM if hasattr(c, "amount_sold") else 0,
                                "amount_bought": c.amount_bought.int64 / STROOPS_PER_XLM if hasattr(c, "amount_bought") else 0,
                            }
                        )

        return {
            "success": success,
            "offer_id": offer_id,
            "offers_claimed": offers_claimed,
            "fee_charged": fee_charged,
        }

    except Exception as e:
        logger.error(f"Failed to decode transaction result XDR: {e}")
        return {
            "success": False,
            "offer_id": None,
            "offers_claimed": [],
            "fee_charged": 0,
            "error": str(e),
        }


# ──────────────────────────────────────────────
# Ledger Entry Parsing
# ──────────────────────────────────────────────


def parse_offer_entry(xdr_base64: str) -> Optional[Dict[str, Any]]:
    """
    Parse an OfferEntry from a base64-encoded LedgerEntry XDR.

    Returns a dict with:
    - offer_id: int
    - seller_id: str (public key)
    - selling_asset: dict with code/issuer
    - buying_asset: dict with code/issuer
    - amount: Decimal
    - price: Decimal (price = price_n / price_d)
    """
    try:
        xdr_bytes = base64.b64decode(xdr_base64)
        entry_data = LedgerEntryData.from_xdr_bytes(xdr_bytes)

        if entry_data.type != LedgerEntryType.OFFER:
            return None

        offer: OfferEntry = entry_data.offer

        # Extract seller public key
        seller_bytes = offer.seller_id.account_id.ed25519.uint256
        seller_pk = Keypair.from_raw_ed25519_public_key(seller_bytes).public_key

        # Extract assets
        selling_asset = _xdr_asset_to_dict(offer.selling)
        buying_asset = _xdr_asset_to_dict(offer.buying)

        # Amount in stroops → XLM
        amount = Decimal(offer.amount.int64) / Decimal(STROOPS_PER_XLM)

        # Price as fraction
        price_n = offer.price.n.int32
        price_d = offer.price.d.int32
        price = Decimal(price_n) / Decimal(price_d) if price_d != 0 else Decimal(0)

        return {
            "offer_id": offer.offer_id.int64,
            "seller_id": seller_pk,
            "selling_asset": selling_asset,
            "buying_asset": buying_asset,
            "amount": amount,
            "price": price,
        }

    except Exception as e:
        logger.error(f"Failed to parse offer entry XDR: {e}")
        return None


def parse_trustline_entry(xdr_base64: str) -> Optional[Dict[str, Any]]:
    """
    Parse a TrustLineEntry from a base64-encoded LedgerEntry XDR.
    """
    try:
        xdr_bytes = base64.b64decode(xdr_base64)
        entry_data = LedgerEntryData.from_xdr_bytes(xdr_bytes)

        if entry_data.type != LedgerEntryType.TRUSTLINE:
            return None

        tl: TrustLineEntry = entry_data.trust_line
        account_bytes = tl.account_id.account_id.ed25519.uint256
        account_pk = Keypair.from_raw_ed25519_public_key(account_bytes).public_key

        asset_info = _xdr_trustline_asset_to_dict(tl.asset)
        balance = Decimal(tl.balance.int64) / Decimal(STROOPS_PER_XLM)

        return {
            "account_id": account_pk,
            "asset": asset_info,
            "balance": balance,
        }

    except Exception as e:
        logger.error(f"Failed to parse trustline entry: {e}")
        return None


def parse_account_entry(xdr_base64: str) -> Optional[Dict[str, Any]]:
    """
    Parse an AccountEntry from a base64-encoded LedgerEntry XDR.
    """
    try:
        xdr_bytes = base64.b64decode(xdr_base64)
        entry_data = LedgerEntryData.from_xdr_bytes(xdr_bytes)

        if entry_data.type != LedgerEntryType.ACCOUNT:
            return None

        account: AccountEntry = entry_data.account
        account_bytes = account.account_id.account_id.ed25519.uint256
        account_pk = Keypair.from_raw_ed25519_public_key(account_bytes).public_key

        balance = Decimal(account.balance.int64) / Decimal(STROOPS_PER_XLM)
        sequence = account.seq_num.sequence_number.int64

        return {
            "account_id": account_pk,
            "balance": balance,
            "sequence": sequence,
        }

    except Exception as e:
        logger.error(f"Failed to parse account entry: {e}")
        return None


# ──────────────────────────────────────────────
# Ledger Key Builders (for getLedgerEntries)
# Compatible with stellar-sdk v13.x
# ──────────────────────────────────────────────


def _build_account_id_xdr(account_id: str) -> AccountID:
    """Helper: builds an AccountID XDR object from a Stellar public key string."""
    pub_key_bytes = Keypair.from_public_key(account_id).raw_public_key()
    return AccountID(
        PublicKey(
            type=PublicKeyType.PUBLIC_KEY_TYPE_ED25519,
            ed25519=Uint256(pub_key_bytes),
        )
    )


def build_account_ledger_key(account_id: str) -> str:
    """
    Builds a base64-encoded LedgerKey for an account.
    Used with the getLedgerEntries RPC method.
    """
    account_xdr = _build_account_id_xdr(account_id)
    ledger_key = LedgerKey(
        type=LedgerEntryType.ACCOUNT,
        account=LedgerKeyAccount(account_id=account_xdr),
    )
    return base64.b64encode(ledger_key.to_xdr_bytes()).decode("utf-8")


def build_offer_ledger_key(seller_id: str, offer_id: int) -> str:
    """
    Builds a base64-encoded LedgerKey for a specific offer.
    """
    seller_xdr = _build_account_id_xdr(seller_id)
    ledger_key = LedgerKey(
        type=LedgerEntryType.OFFER,
        offer=LedgerKeyOffer(seller_id=seller_xdr, offer_id=Int64(offer_id)),
    )
    return base64.b64encode(ledger_key.to_xdr_bytes()).decode("utf-8")


def build_trustline_ledger_key(account_id: str, asset: Asset) -> str:
    """
    Builds a base64-encoded LedgerKey for a trustline.
    """
    account_xdr = _build_account_id_xdr(account_id)

    # Convert Asset to TrustLineAsset XDR (v13 constructor style)
    if asset.is_native():
        tl_asset = TrustLineAsset(type=AssetType.ASSET_TYPE_NATIVE)
    else:
        # Convert via the Asset's own XDR representation
        asset_xdr = asset.to_xdr_object()
        if asset_xdr.type == AssetType.ASSET_TYPE_CREDIT_ALPHANUM4:
            tl_asset = TrustLineAsset(
                type=AssetType.ASSET_TYPE_CREDIT_ALPHANUM4,
                alpha_num4=asset_xdr.alpha_num4,
            )
        else:
            tl_asset = TrustLineAsset(
                type=AssetType.ASSET_TYPE_CREDIT_ALPHANUM12,
                alpha_num12=asset_xdr.alpha_num12,
            )

    ledger_key = LedgerKey(
        type=LedgerEntryType.TRUSTLINE,
        trust_line=LedgerKeyTrustLine(account_id=account_xdr, asset=tl_asset),
    )
    return base64.b64encode(ledger_key.to_xdr_bytes()).decode("utf-8")


# ──────────────────────────────────────────────
# Internal Helpers
# ──────────────────────────────────────────────


def _xdr_asset_to_dict(xdr_asset) -> Dict[str, str]:
    """Convert an XDR Asset to a simple dictionary."""
    if xdr_asset.type == AssetType.ASSET_TYPE_NATIVE:
        return {"type": "native", "code": "XLM", "issuer": None}
    elif xdr_asset.type == AssetType.ASSET_TYPE_CREDIT_ALPHANUM4:
        code = xdr_asset.alpha_num4.asset_code.asset_code4.decode().rstrip("\x00")
        issuer_bytes = xdr_asset.alpha_num4.issuer.account_id.ed25519.uint256
        issuer = Keypair.from_raw_ed25519_public_key(issuer_bytes).public_key
        return {"type": "credit_alphanum4", "code": code, "issuer": issuer}
    elif xdr_asset.type == AssetType.ASSET_TYPE_CREDIT_ALPHANUM12:
        code = xdr_asset.alpha_num12.asset_code.asset_code12.decode().rstrip("\x00")
        issuer_bytes = xdr_asset.alpha_num12.issuer.account_id.ed25519.uint256
        issuer = Keypair.from_raw_ed25519_public_key(issuer_bytes).public_key
        return {"type": "credit_alphanum12", "code": code, "issuer": issuer}
    return {"type": "unknown", "code": "", "issuer": None}


def _xdr_trustline_asset_to_dict(tl_asset) -> Dict[str, str]:
    """Convert an XDR TrustLineAsset to a simple dictionary."""
    if tl_asset.type == AssetType.ASSET_TYPE_NATIVE:
        return {"type": "native", "code": "XLM", "issuer": None}
    elif tl_asset.type == AssetType.ASSET_TYPE_CREDIT_ALPHANUM4:
        code = tl_asset.alpha_num4.asset_code.asset_code4.decode().rstrip("\x00")
        issuer_bytes = tl_asset.alpha_num4.issuer.account_id.ed25519.uint256
        issuer = Keypair.from_raw_ed25519_public_key(issuer_bytes).public_key
        return {"type": "credit_alphanum4", "code": code, "issuer": issuer}
    elif tl_asset.type == AssetType.ASSET_TYPE_CREDIT_ALPHANUM12:
        code = tl_asset.alpha_num12.asset_code.asset_code12.decode().rstrip("\x00")
        issuer_bytes = tl_asset.alpha_num12.issuer.account_id.ed25519.uint256
        issuer = Keypair.from_raw_ed25519_public_key(issuer_bytes).public_key
        return {"type": "credit_alphanum12", "code": code, "issuer": issuer}
    return {"type": "unknown", "code": "", "issuer": None}
