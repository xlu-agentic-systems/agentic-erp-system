"""Natural-language adapter for safe ERP workflow commands."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import re

import erp_core


@dataclass(frozen=True)
class AdaptiveResult:
    success: bool
    changed: bool
    action: str
    message: str


def execute_goal(goal: str, data: erp_core.ERPData, as_of: date | None = None) -> tuple[erp_core.ERPData, AdaptiveResult]:
    """Execute a constrained ERP command from natural language.

    Only explicit operational commands mutate state. Ambiguous requests return
    an actionable message and leave the ERP data unchanged.
    """

    as_of = as_of or date.today()
    normalized = goal.strip()
    if not normalized:
        return data, _no_match()

    try:
        if _looks_like_receive_po(normalized):
            po_id = _extract_document_id(normalized, "PO")
            updated, po = erp_core.receive_purchase_order(data, po_id, as_of)
            return updated, AdaptiveResult(True, True, "receive_purchase_order", f"Received {po.id}; inventory is updated.")

        if _looks_like_invoice_payment(normalized):
            invoice_id = _extract_document_id(normalized, "INV")
            amount = _extract_payment_amount(normalized)
            updated, invoice = erp_core.apply_invoice_payment(data, invoice_id, amount, as_of)
            amount_text = f" of {erp_core.money(amount)}" if amount is not None else ""
            return updated, AdaptiveResult(True, True, "record_invoice_payment", f"Recorded payment{amount_text} for {invoice.id}; balance is {invoice.balance_due}.")

        if _looks_like_create_po(normalized):
            product = _extract_product_reference(normalized, data)
            quantity = _extract_quantity(normalized)
            updated, po = erp_core.create_purchase_order(data, product, quantity, None, as_of)
            sku = erp_core.find_product(updated, product).sku if erp_core.find_product(updated, product) else product
            return updated, AdaptiveResult(True, True, "create_purchase_order", f"Created {po.id} for {sku} with {po.lines[0].quantity} units.")
    except ValueError as exc:
        return data, AdaptiveResult(False, False, "error", str(exc))

    return data, _no_match()


def _no_match() -> AdaptiveResult:
    return AdaptiveResult(
        success=False,
        changed=False,
        action="unknown",
        message="Try commands like 'reorder PUMP-A', 'receive PO-1001', or 'mark INV-9001 paid'.",
    )


def _looks_like_create_po(text: str) -> bool:
    q = text.lower()
    return any(
        phrase in q
        for phrase in (
            "reorder",
            "restock",
            "buy",
            "procure",
            "create po",
            "create a po",
            "create purchase order",
            "purchase order for",
            "order more",
        )
    )


def _looks_like_receive_po(text: str) -> bool:
    q = text.lower()
    return "po" in q and any(phrase in q for phrase in ("receive", "received", "arrived", "goods receipt", "mark purchase order"))


def _looks_like_invoice_payment(text: str) -> bool:
    q = text.lower()
    return ("inv" in q or "invoice" in q) and any(
        phrase in q for phrase in ("paid", "pay", "payment", "collect", "received payment", "record payment")
    )


def _extract_document_id(text: str, prefix: str) -> str:
    pattern = rf"\b{prefix}\s*-?\s*(\d+)\b"
    match = re.search(pattern, text, flags=re.IGNORECASE)
    if not match:
        raise ValueError(f"Could not find {prefix} document ID")
    return f"{prefix}-{match.group(1)}"


def _extract_quantity(text: str) -> int | None:
    cleaned = re.sub(r"\b(?:PO|INV)\s*-?\s*\d+\b", "", text, flags=re.IGNORECASE)
    match = re.search(r"\b(\d+)\b", cleaned)
    return int(match.group(1)) if match else None


def _extract_payment_amount(text: str) -> str | None:
    cleaned = re.sub(r"\bINV\s*-?\s*\d+\b", "", text, flags=re.IGNORECASE)
    match = re.search(r"(?:\$|usd\s*)?(\d+(?:\.\d{1,2})?)\b", cleaned, flags=re.IGNORECASE)
    return match.group(1) if match else None


def _extract_product_reference(text: str, data: erp_core.ERPData) -> str:
    best_match: tuple[int, str] | None = None
    haystack = _search_key(text)
    for product in data.products:
        candidates = (product.sku, product.id, product.name)
        for candidate in candidates:
            key = _search_key(candidate)
            if key and key in haystack:
                score = len(key)
                if best_match is None or score > best_match[0]:
                    best_match = (score, product.sku)
    if best_match:
        return best_match[1]
    raise ValueError("Could not identify a product to reorder")


def _search_key(value: object) -> str:
    return "".join(ch for ch in str(value).lower() if ch.isalnum())
