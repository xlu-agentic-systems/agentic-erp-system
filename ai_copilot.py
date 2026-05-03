"""Read-only AI copilot layer for the ERP demo.

The module intentionally uses deterministic rules and lightweight intent
matching. That keeps recommendations explainable while still showing how an AI
ERP assistant can sit across sales, inventory, procurement, and finance.
"""

from __future__ import annotations

import inspect
from dataclasses import dataclass
from datetime import date
from typing import Iterable


@dataclass(frozen=True)
class Insight:
    type: str
    severity: str
    title: str
    entity: str
    reason: str
    recommended_action: str


def _money(value: float) -> str:
    return f"${value:,.0f}"


def _get_attr(item: object, name: str, default: object = None) -> object:
    if isinstance(item, dict):
        return item.get(name, default)
    return getattr(item, name, default)


def _product_inventory_pair(item: object) -> tuple[object, object | None]:
    if isinstance(item, tuple) and len(item) == 2:
        return item[0], item[1]
    return item, None


def _numeric(value: object, default: float = 0.0) -> float:
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _items(data: object, name: str) -> list[object]:
    value = _get_attr(data, name, [])
    return list(value or [])


def _call(module: object, name: str, data: object, default: object) -> object:
    func = getattr(module, name, None)
    if callable(func):
        if _callable_accepts(func, data):
            return func(data)
        if _callable_accepts(func):
            return func()
    return default


def _callable_accepts(func: object, *args: object) -> bool:
    try:
        inspect.signature(func).bind(*args)
    except TypeError:
        return False
    except ValueError:
        return True
    return True


def _as_dashboard_insights(data: object) -> list[Insight]:
    """Build insights from already-renderable dashboard dictionaries."""
    insights: list[Insight] = []
    for risk in _items(data, "risk_flags"):
        level = str(_get_attr(risk, "level", _get_attr(risk, "severity", "info"))).lower()
        title = str(_get_attr(risk, "title", "Risk flag"))
        detail = str(_get_attr(risk, "detail", _get_attr(risk, "reason", "Needs review.")))
        if "stock" in title.lower():
            insight_type = "inventory"
            action = "Review replenishment and open purchase orders."
        elif "po" in title.lower() or "supplier" in title.lower() or "vendor" in title.lower():
            insight_type = "procurement"
            action = "Contact the supplier and confirm the recovery date."
        elif "invoice" in title.lower() or "cash" in title.lower() or "ar" in title.lower():
            insight_type = "finance"
            action = "Review collections and near-term cash commitments."
        else:
            insight_type = "operations"
            action = "Assign an owner and review the source ERP record."
        insights.append(
            Insight(
                type=insight_type,
                severity="high" if level == "high" else "medium" if level == "medium" else "low",
                title=title,
                entity=title,
                reason=detail,
                recommended_action=action,
            )
        )
    return insights


def build_insights(data: object, erp_core_module: object | None = None) -> list[Insight]:
    """Build auditable cross-module ERP risk flags."""
    insights: list[Insight] = []

    if erp_core_module is not None:
        low_stock = _call(erp_core_module, "low_stock_items", data, [])
        delayed_pos = _call(erp_core_module, "delayed_purchase_orders", data, [])
        overdue_invoices = _call(erp_core_module, "overdue_invoices", data, [])
        cash_projection = _call(erp_core_module, "cash_projection_details", data, {})
    else:
        low_stock = []
        delayed_pos = []
        overdue_invoices = []
        cash_projection = {}

    for item in low_stock:
        product, inventory = _product_inventory_pair(item)
        sku = str(_get_attr(product, "sku", _get_attr(inventory, "product_id", "unknown")))
        name = str(_get_attr(product, "name", sku))
        on_hand = int(_get_attr(inventory, "available_quantity", _get_attr(product, "on_hand", _get_attr(product, "quantity_on_hand", 0))) or 0)
        reorder_point = int(_get_attr(product, "reorder_point", 0) or 0)
        severity = "high" if on_hand <= max(1, reorder_point // 2) else "medium"
        insights.append(
            Insight(
                type="inventory",
                severity=severity,
                title=f"Low stock: {name}",
                entity=sku,
                reason=f"{on_hand} units on hand against a reorder point of {reorder_point}.",
                recommended_action=f"Create or expedite a purchase order for {sku}.",
            )
        )

    for po in delayed_pos:
        po_id = str(_get_attr(po, "id", _get_attr(po, "po_id", "purchase order")))
        vendor = str(_get_attr(po, "vendor", _get_attr(po, "vendor_name", _get_attr(po, "vendor_id", "supplier"))))
        due_date = _get_attr(po, "expected_date", _get_attr(po, "due_date", None))
        insights.append(
            Insight(
                type="procurement",
                severity="high",
                title=f"Delayed purchase order: {po_id}",
                entity=po_id,
                reason=f"{vendor} has not delivered an order expected on {due_date}.",
                recommended_action="Contact the vendor and review downstream sales-order impact.",
            )
        )

    for invoice in overdue_invoices:
        invoice_id = str(_get_attr(invoice, "id", _get_attr(invoice, "invoice_id", "invoice")))
        customer = str(_get_attr(invoice, "customer", _get_attr(invoice, "customer_name", _get_attr(invoice, "customer_id", "customer"))))
        amount = _numeric(_get_attr(invoice, "balance_due", _get_attr(invoice, "amount", _get_attr(invoice, "balance", 0.0))))
        insights.append(
            Insight(
                type="finance",
                severity="medium",
                title=f"Overdue receivable: {invoice_id}",
                entity=invoice_id,
                reason=f"{customer} owes {_money(amount)} past the due date.",
                recommended_action="Send a payment follow-up and include the invoice aging detail.",
            )
        )

    if isinstance(cash_projection, dict):
        projected_cash = _numeric(cash_projection.get("projected_cash", cash_projection.get("ending_cash", 0)))
        threshold = _numeric(cash_projection.get("threshold", 50000), 50000)
        if projected_cash < threshold:
            insights.append(
                Insight(
                    type="cashflow",
                    severity="high",
                    title="Projected cash below threshold",
                    entity="cash",
                    reason=f"Projected cash is {_money(projected_cash)}, below the {_money(threshold)} operating threshold.",
                    recommended_action="Prioritize overdue receivable collection and review noncritical payables.",
                )
            )

    if not insights:
        insights = _as_dashboard_insights(data)

    return sorted(insights, key=lambda insight: {"high": 0, "medium": 1, "low": 2}.get(insight.severity, 3))


def reorder_recommendations(data: object, erp_core_module: object | None = None) -> list[dict[str, object]]:
    """Recommend reorder actions using ERP inventory and vendor data."""
    if erp_core_module is not None:
        low_stock = _call(erp_core_module, "low_stock_items", data, [])
    else:
        low_stock = []

    vendors_by_sku: dict[str, list[object]] = {}
    for vendor in _items(data, "vendors"):
        for sku in _get_attr(vendor, "supplied_skus", []) or []:
            vendors_by_sku.setdefault(str(sku), []).append(vendor)

    recommendations: list[dict[str, object]] = []
    for item in low_stock:
        product, inventory = _product_inventory_pair(item)
        sku = str(_get_attr(product, "sku", _get_attr(inventory, "product_id", "")))
        reorder_point = int(_get_attr(product, "reorder_point", 0) or 0)
        on_hand = int(_get_attr(inventory, "available_quantity", _get_attr(product, "on_hand", _get_attr(product, "quantity_on_hand", 0))) or 0)
        target = max(reorder_point * 2, reorder_point + 10)
        quantity = max(target - on_hand, 1)
        vendors = vendors_by_sku.get(sku, [])
        preferred = sorted(
            vendors,
            key=lambda vendor: (
                -float(_get_attr(vendor, "reliability", 0) or 0),
                int(_get_attr(vendor, "lead_time_days", 999) or 999),
            ),
        )
        best_vendor = preferred[0] if preferred else None
        recommendations.append(
            {
                "sku": sku,
                "product": _get_attr(product, "name", sku),
                "quantity": quantity,
                "vendor": _get_attr(best_vendor, "name", "Review approved supplier list") if best_vendor else "Review approved supplier list",
                "reason": f"Reorder {quantity} units to restore stock toward {target} units.",
                "risk": "Open sales orders may be delayed if replenishment is not started.",
            }
        )
    return recommendations


def dashboard_reorder_recommendations(data: object) -> list[dict[str, object]]:
    recs: list[dict[str, object]] = []
    for item in _items(data, "inventory"):
        status = str(_get_attr(item, "status", "")).lower()
        if status != "low":
            continue
        sku = str(_get_attr(item, "sku", "SKU"))
        stock = int(_numeric(_get_attr(item, "stock", 0)))
        quantity = max(20, stock)
        recs.append(
            {
                "sku": sku,
                "product": _get_attr(item, "item", sku),
                "quantity": quantity,
                "vendor": "best available supplier",
                "reason": f"Inventory status is {status}; bring available stock above the reorder band.",
                "risk": "Customer orders may be delayed if replenishment slips.",
            }
        )
    return recs


def role_summary(role: str, data: object, erp_core_module: object | None = None) -> dict[str, object]:
    """Return a role-specific operating summary."""
    normalized = role.lower().strip()
    insights = build_insights(data, erp_core_module)

    filters = {
        "cfo": {"finance", "cashflow"},
        "operations": {"inventory", "procurement"},
        "procurement": {"inventory", "procurement"},
        "sales": {"inventory", "finance"},
    }
    wanted = filters.get(normalized, {"inventory", "procurement", "finance", "cashflow"})
    relevant = [insight for insight in insights if insight.type in wanted]
    high_count = sum(1 for insight in relevant if insight.severity == "high")

    if not relevant:
        headline = "No urgent exceptions for this role."
    elif high_count:
        headline = f"{high_count} high-priority exception{'s' if high_count != 1 else ''} need attention."
    else:
        headline = f"{len(relevant)} operating item{'s' if len(relevant) != 1 else ''} should be monitored."

    return {
        "role": role,
        "headline": headline,
        "focus": [insight.title for insight in relevant[:4]],
        "next_action": relevant[0].recommended_action if relevant else "Keep monitoring the shared ERP dashboard.",
    }


def workflow_suggestions(data: object, erp_core_module: object | None = None) -> list[str]:
    suggestions: list[str] = []
    for recommendation in reorder_recommendations(data, erp_core_module):
        suggestions.append(
            f"Draft PO for {recommendation['sku']} with {recommendation['vendor']} for {recommendation['quantity']} units."
        )
    for insight in build_insights(data, erp_core_module):
        if insight.type in {"finance", "procurement", "cashflow"}:
            suggestions.append(insight.recommended_action)
    return suggestions[:8]


def answer_question(question: str, data: object, erp_core_module: object | None = None) -> str:
    """Answer a natural-language ERP question through constrained intents."""
    q = question.lower().strip()
    insights = build_insights(data, erp_core_module)

    if not q:
        return "Ask about stockouts, delayed vendors, overdue invoices, cashflow, or open orders."

    if any(token in q for token in ("stock", "inventory", "reorder", "sku")):
        recs = reorder_recommendations(data, erp_core_module)
        if not recs:
            recs = dashboard_reorder_recommendations(data)
        if not recs:
            return "No products are currently below reorder point."
        return " ".join(
            f"{rec['sku']} needs {rec['quantity']} units from {rec['vendor']}."
            for rec in recs[:4]
        )

    if any(token in q for token in ("vendor", "supplier", "delay", "late po", "purchase")):
        procurement = [insight for insight in insights if insight.type == "procurement"]
        if not procurement:
            return "No delayed purchase orders are currently flagged."
        return " ".join(f"{item.title}: {item.reason}" for item in procurement[:4])

    if any(token in q for token in ("invoice", "receivable", "overdue", "customer owes")):
        finance = [insight for insight in insights if insight.type == "finance"]
        if not finance:
            return "No overdue customer invoices are currently flagged."
        return " ".join(f"{item.title}: {item.reason}" for item in finance[:4])

    if any(token in q for token in ("cash", "cashflow", "runway", "payable")):
        if erp_core_module is not None:
            projection = _call(erp_core_module, "cash_projection_details", data, {})
        else:
            projection = {}
        if isinstance(projection, dict) and projection:
            cash = _money(float(projection.get("projected_cash", projection.get("ending_cash", 0)) or 0))
            inflow = _money(float(projection.get("expected_inflows", 0) or 0))
            outflow = _money(float(projection.get("expected_outflows", 0) or 0))
            return f"Projected cash is {cash}. Expected inflows are {inflow}; expected outflows are {outflow}."
        kpis = _items(data, "kpis")
        cash_kpi = next((kpi for kpi in kpis if "cash" in str(_get_attr(kpi, "label", "")).lower()), None)
        if cash_kpi:
            return f"{_get_attr(cash_kpi, 'label', 'Cash')}: {_get_attr(cash_kpi, 'value', 'unknown')} ({_get_attr(cash_kpi, 'trend', 'current dashboard')})."
        return "Cash projection data is not available."

    if any(token in q for token in ("open order", "sales order", "blocked", "fulfill")):
        open_orders: Iterable[object] = _call(erp_core_module, "open_sales_orders", data, []) if erp_core_module else []
        orders = list(open_orders)
        if not orders:
            return "No open sales orders are waiting for fulfillment."
        return " ".join(
            f"{_get_attr(order, 'id', 'order')} for {_get_attr(order, 'customer', _get_attr(order, 'customer_name', _get_attr(order, 'customer_id', 'customer')))} is {_get_attr(order, 'status', 'open')}."
            for order in orders[:5]
        )

    high = [insight for insight in insights if insight.severity == "high"]
    if high:
        return "Top priority: " + " ".join(f"{item.title}. {item.recommended_action}" for item in high[:3])
    return "The ERP copilot found no urgent exceptions. Try asking about inventory, vendors, invoices, cashflow, or open orders."


def ask_erp(question: str, data: object) -> str:
    return answer_question(question, data)


def generated_at() -> str:
    return date.today().isoformat()
