"""Natural-language adapter for safe ERP workflow commands."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
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
    if _looks_negated(normalized):
        return data, _negated_command()

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


def preview_goal(goal: str, data: erp_core.ERPData, as_of: date | None = None) -> AdaptiveResult:
    """Return the deterministic action that would run without mutating ERP data."""

    as_of = as_of or date.today()
    normalized = goal.strip()
    if not normalized:
        return _no_match()
    if _looks_negated(normalized):
        return _negated_command()

    try:
        if _looks_like_receive_po(normalized):
            po = _find_purchase_order(data, _extract_document_id(normalized, "PO"))
            if erp_core.status_key(po.status) == "received":
                raise ValueError(f"{po.id} is already received")
            quantity = sum(line.quantity for line in po.lines)
            return AdaptiveResult(True, False, "receive_purchase_order", f"Preview: receive {po.id} and add {quantity} inventory unit(s).")

        if _looks_like_invoice_payment(normalized):
            invoice = _find_invoice(data, _extract_document_id(normalized, "INV"))
            if invoice.balance_due <= 0 or erp_core.status_key(invoice.status) == "paid":
                raise ValueError(f"{invoice.id} is already paid")
            amount_raw = _extract_payment_amount(normalized)
            payment = invoice.balance_due if amount_raw is None else erp_core.money(amount_raw)
            if payment <= 0:
                raise ValueError("payment amount must be positive")
            if payment > invoice.balance_due:
                raise ValueError("payment amount cannot exceed invoice balance")
            projected_balance = invoice.balance_due - payment
            return AdaptiveResult(True, False, "record_invoice_payment", f"Preview: record payment of {payment} for {invoice.id}; balance would be {projected_balance}.")

        if _looks_like_create_po(normalized):
            reference = _extract_product_reference(normalized, data)
            product = erp_core.find_product(data, reference)
            if product is None:
                raise ValueError(f"Unknown product: {reference}")
            quantity = _extract_quantity(normalized) or erp_core.reorder_quantity(data, product)
            if quantity <= 0:
                raise ValueError("quantity must be positive")
            vendor = erp_core.find_vendor_for_product(data, product)
            po_id = erp_core.next_document_id((po.id for po in data.purchase_orders), "PO")
            expected_date = as_of + timedelta(days=vendor.lead_time_days)
            return AdaptiveResult(True, False, "create_purchase_order", f"Preview: create {po_id} for {product.sku} with {quantity} units from {vendor.name} expected on {expected_date}.")
    except ValueError as exc:
        return AdaptiveResult(False, False, "error", str(exc))

    return _no_match()


def _no_match() -> AdaptiveResult:
    return AdaptiveResult(
        success=False,
        changed=False,
        action="unknown",
        message="Try commands like 'reorder PUMP-A', 'receive PO-1001', or 'mark INV-9001 paid'.",
    )


def _negated_command() -> AdaptiveResult:
    return AdaptiveResult(
        success=False,
        changed=False,
        action="negated",
        message="No action taken because the command appears to be negated.",
    )


def _looks_negated(text: str) -> bool:
    q = text.lower()
    return any(phrase in q for phrase in ("don't ", "do not ", "dont ", "never "))


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


def _find_purchase_order(data: erp_core.ERPData, purchase_order_id: str) -> erp_core.PurchaseOrder:
    wanted = erp_core.normalize_document_id(purchase_order_id, "PO")
    for po in data.purchase_orders:
        if _search_key(po.id) == _search_key(wanted):
            return po
    raise ValueError(f"Unknown purchase order: {purchase_order_id}")


def _find_invoice(data: erp_core.ERPData, invoice_id: str) -> erp_core.Invoice:
    wanted = erp_core.normalize_document_id(invoice_id, "INV")
    for invoice in data.invoices:
        if _search_key(invoice.id) == _search_key(wanted):
            return invoice
    raise ValueError(f"Unknown invoice: {invoice_id}")


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
