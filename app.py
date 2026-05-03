"""Dependency-free ERP dashboard HTTP app.

Run with:
    python3 app.py
"""

from __future__ import annotations

import html
import importlib
import inspect
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs


BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8000
APP_VERSION = os.environ.get("APP_VERSION", "dev")
DEFAULT_MAX_POST_BODY_BYTES = 64 * 1024


class RequestTooLarge(ValueError):
    pass


def load_optional_module(name: str) -> Any | None:
    try:
        return importlib.import_module(name)
    except ModuleNotFoundError as exc:
        if exc.name != name:
            raise
        return None


ERP_CORE = load_optional_module("erp_core")
AI_COPILOT = load_optional_module("ai_copilot")
ADAPTIVE_ERP = load_optional_module("adaptive_erp")
ERP_STATE = load_optional_module("erp_state")


def callable_accepts(func: Any, *args: Any) -> bool:
    try:
        inspect.signature(func).bind(*args)
    except TypeError:
        return False
    except ValueError:
        return True
    return True


def call_first(module: Any | None, names: tuple[str, ...], *args: Any) -> Any | None:
    if module is None:
        return None
    for name in names:
        func = getattr(module, name, None)
        if callable(func) and callable_accepts(func, *args):
            return func(*args)
        if callable(func) and callable_accepts(func):
            return func()
    return None


def as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, dict):
        for key in ("items", "results", "records", "data"):
            if isinstance(value.get(key), list):
                return value[key]
        return [value]
    return []


def money(value: Any) -> str:
    try:
        return f"${float(value):,.0f}"
    except (TypeError, ValueError):
        return str(value or "$0")


def number(value: Any) -> str:
    try:
        return f"{float(value):,.0f}"
    except (TypeError, ValueError):
        return str(value or "0")


def text(value: Any, fallback: str = "") -> str:
    if value is None:
        return fallback
    return str(value)


def max_post_body_bytes() -> int:
    raw_value = os.environ.get("MAX_POST_BODY_BYTES")
    if raw_value is None:
        return DEFAULT_MAX_POST_BODY_BYTES
    try:
        parsed = int(raw_value)
    except ValueError:
        return DEFAULT_MAX_POST_BODY_BYTES
    return parsed if parsed > 0 else DEFAULT_MAX_POST_BODY_BYTES


def parse_content_length(value: str | None, max_length: int | None = None) -> int:
    length = int(value or "0")
    if length < 0:
        raise ValueError("Content-Length must be non-negative")
    if max_length is not None and length > max_length:
        raise RequestTooLarge(f"Content-Length exceeds {max_length} bytes")
    return length


def pick(record: Any, *keys: str, fallback: Any = "") -> Any:
    if isinstance(record, dict):
        for key in keys:
            if key in record and record[key] not in (None, ""):
                return record[key]
    for key in keys:
        if hasattr(record, key):
            value = getattr(record, key)
            if value not in (None, ""):
                return value
    return fallback


def seeded_data() -> Any | None:
    return call_first(ERP_CORE, ("seed_erp_data", "sample_data", "get_seed_data"))


def current_erp_data() -> Any | None:
    if ERP_STATE is not None:
        return ERP_STATE.load_data()
    return seeded_data()


def resolve_name(records: Any, record_id: Any) -> str:
    for record in as_list(records):
        if pick(record, "id") == record_id:
            return text(pick(record, "name", fallback=record_id))
    return text(record_id)


def product_lookup(data: Any) -> dict[Any, Any]:
    return {pick(product, "id"): product for product in as_list(pick(data, "products", fallback=[]))}


def build_seed_dashboard(seed: Any) -> dict[str, Any]:
    products = product_lookup(seed)
    customers = pick(seed, "customers", fallback=[])
    vendors = pick(seed, "vendors", fallback=[])
    inventory = as_list(pick(seed, "inventory", fallback=[]))
    sales_orders = as_list(pick(seed, "sales_orders", fallback=[]))
    purchase_orders = as_list(pick(seed, "purchase_orders", fallback=[]))
    invoices = as_list(pick(seed, "invoices", fallback=[]))

    inventory_value = call_first(ERP_CORE, ("inventory_value",), seed)
    open_orders = as_list(call_first(ERP_CORE, ("open_sales_orders",), seed)) or [
        order for order in sales_orders if text(pick(order, "status")).lower() not in {"cancelled", "closed", "shipped", "invoiced"}
    ]
    cash_projection = call_first(ERP_CORE, ("cash_projection",), seed)
    receivable_balance = sum(
        float(pick(invoice, "balance_due", "amount", fallback=0) or 0)
        for invoice in invoices
        if text(pick(invoice, "status")).lower() != "paid"
    )

    low_stock_pairs = as_list(call_first(ERP_CORE, ("low_stock_items",), seed))
    delayed_pos = as_list(call_first(ERP_CORE, ("delayed_purchase_orders",), seed))
    overdue_invoices = as_list(call_first(ERP_CORE, ("overdue_invoices",), seed))

    risk_flags = []
    for pair in low_stock_pairs:
        product, item = pair if isinstance(pair, tuple) and len(pair) == 2 else (products.get(pick(pair, "product_id")), pair)
        risk_flags.append(
            {
                "level": "High",
                "title": f"Low stock: {pick(product, 'sku', 'name', fallback='SKU')}",
                "detail": f"{pick(item, 'available_quantity', 'quantity_on_hand', fallback=0)} available against reorder point {pick(product, 'reorder_point', fallback='n/a')}.",
            }
        )
    for po in delayed_pos:
        risk_flags.append(
            {
                "level": "High",
                "title": f"Delayed purchase order: {pick(po, 'id', fallback='PO')}",
                "detail": f"{resolve_name(vendors, pick(po, 'vendor_id'))} expected delivery on {pick(po, 'expected_date', fallback='unknown')}.",
            }
        )
    for invoice in overdue_invoices:
        risk_flags.append(
            {
                "level": "Medium",
                "title": f"Overdue receivable: {pick(invoice, 'id', fallback='Invoice')}",
                "detail": f"{resolve_name(customers, pick(invoice, 'customer_id'))} has {money(pick(invoice, 'balance_due', 'amount', fallback=0))} outstanding.",
            }
        )

    roles = []
    if AI_COPILOT is not None:
        for role_name in ("Operations", "Sales", "Finance"):
            summary_func = getattr(AI_COPILOT, "role_summary", None)
            if callable(summary_func):
                if callable_accepts(summary_func, role_name, seed, ERP_CORE):
                    summary = summary_func(role_name, seed, ERP_CORE)
                elif callable_accepts(summary_func, role_name, seed):
                    summary = summary_func(role_name, seed)
                else:
                    summary = None
                if summary:
                    roles.append(
                        {
                            "role": role_name,
                            "summary": text(pick(summary, "headline", "summary", fallback="No urgent exceptions.")),
                        }
                    )

    return {
        "kpis": [
            {"label": "Inventory value", "value": money(inventory_value), "trend": f"{len(inventory)} stocked items"},
            {"label": "Open sales orders", "value": number(len(open_orders)), "trend": "Awaiting fulfillment"},
            {"label": "Receivables due", "value": money(receivable_balance), "trend": f"{len(overdue_invoices)} overdue"},
            {"label": "30-day cash", "value": money(cash_projection), "trend": "Projected balance"},
        ],
        "risk_flags": risk_flags or FALLBACK_DATA["risk_flags"],
        "roles": roles or FALLBACK_DATA["roles"],
        "inventory": [
            {
                "sku": pick(products.get(pick(item, "product_id")), "sku", fallback=pick(item, "product_id")),
                "item": pick(products.get(pick(item, "product_id")), "name", fallback="Product"),
                "stock": pick(item, "available_quantity", "quantity_on_hand", fallback=0),
                "status": "Low"
                if any(
                    isinstance(pair, tuple) and len(pair) == 2 and pick(pair[1], "product_id") == pick(item, "product_id")
                    for pair in low_stock_pairs
                )
                else "Healthy",
            }
            for item in inventory
        ],
        "sales_orders": [
            {
                "id": pick(order, "id", fallback="SO"),
                "customer": resolve_name(customers, pick(order, "customer_id")),
                "total": pick(order, "total", fallback=0),
                "status": pick(order, "status", fallback="open"),
            }
            for order in sales_orders
        ],
        "purchase_orders": [
            {
                "id": pick(order, "id", fallback="PO"),
                "supplier": resolve_name(vendors, pick(order, "vendor_id")),
                "total": pick(order, "total", fallback=0),
                "status": pick(order, "status", fallback="open"),
            }
            for order in purchase_orders
        ],
        "invoices": [
            {
                "id": pick(invoice, "id", fallback="INV"),
                "customer": resolve_name(customers, pick(invoice, "customer_id")),
                "amount": pick(invoice, "balance_due", "amount", fallback=0),
                "status": "Overdue" if invoice in overdue_invoices else pick(invoice, "status", fallback="open"),
            }
            for invoice in invoices
        ],
        "_seed": seed,
    }


FALLBACK_DATA = {
    "kpis": [
        {"label": "Monthly revenue", "value": "$482,000", "trend": "+8.4%"},
        {"label": "Open orders", "value": "38", "trend": "12 due this week"},
        {"label": "Inventory turns", "value": "5.7x", "trend": "Stable"},
        {"label": "Cash due", "value": "$126,000", "trend": "Next 30 days"},
    ],
    "risk_flags": [
        {"level": "High", "title": "Low stock: BRG-142", "detail": "Projected stockout in 5 days."},
        {"level": "Medium", "title": "Invoice aging", "detail": "4 invoices are more than 45 days old."},
        {"level": "Medium", "title": "Supplier delay", "detail": "PO-1048 has slipped beyond ETA."},
    ],
    "roles": [
        {"role": "Operations", "summary": "Watch stockouts and late purchase orders."},
        {"role": "Sales", "summary": "Prioritize fulfillment for confirmed enterprise orders."},
        {"role": "Finance", "summary": "Follow up on aged receivables and payment holds."},
    ],
    "inventory": [
        {"sku": "BRG-142", "item": "Bearing Assembly", "stock": 18, "status": "Low"},
        {"sku": "VAL-220", "item": "Valve Kit", "stock": 146, "status": "Healthy"},
        {"sku": "PMP-018", "item": "Pump Housing", "stock": 42, "status": "Watch"},
    ],
    "sales_orders": [
        {"id": "SO-2042", "customer": "Northwind Energy", "total": 84200, "status": "Ready to ship"},
        {"id": "SO-2043", "customer": "Summit Works", "total": 37650, "status": "Awaiting parts"},
        {"id": "SO-2044", "customer": "Harbor Industrial", "total": 12400, "status": "Confirmed"},
    ],
    "purchase_orders": [
        {"id": "PO-1048", "supplier": "Acme Components", "total": 28400, "status": "Delayed"},
        {"id": "PO-1049", "supplier": "Metro Metals", "total": 16100, "status": "In transit"},
        {"id": "PO-1050", "supplier": "Delta Packaging", "total": 4300, "status": "Ordered"},
    ],
    "invoices": [
        {"id": "INV-9008", "customer": "Northwind Energy", "amount": 84200, "status": "Sent"},
        {"id": "INV-9009", "customer": "Pioneer Parts", "amount": 18800, "status": "Overdue"},
        {"id": "INV-9010", "customer": "Harbor Industrial", "amount": 12400, "status": "Draft"},
    ],
    "fulfillment_risks": [],
}


def normalize_kpis(value: Any) -> list[dict[str, str]]:
    records = as_list(value)
    if not records:
        return FALLBACK_DATA["kpis"]
    kpis = []
    for record in records:
        label = pick(record, "label", "name", "title", fallback="KPI")
        raw_value = pick(record, "value", "amount", "count", fallback="0")
        trend = pick(record, "trend", "change", "detail", "description", fallback="")
        kpis.append({"label": text(label), "value": text(raw_value), "trend": text(trend)})
    return kpis or FALLBACK_DATA["kpis"]


def normalize_risks(value: Any) -> list[dict[str, str]]:
    records = as_list(value)
    if not records:
        return FALLBACK_DATA["risk_flags"]
    risks = []
    for record in records:
        risks.append(
            {
                "level": text(pick(record, "level", "severity", "priority", fallback="Info")),
                "title": text(pick(record, "title", "name", "issue", fallback="Risk flag")),
                "detail": text(pick(record, "detail", "description", "summary", fallback="Needs review.")),
            }
        )
    return risks or FALLBACK_DATA["risk_flags"]


def normalize_roles(value: Any) -> list[dict[str, str]]:
    records = as_list(value)
    if not records:
        return FALLBACK_DATA["roles"]
    roles = []
    for record in records:
        roles.append(
            {
                "role": text(pick(record, "role", "name", "team", fallback="Role")),
                "summary": text(pick(record, "summary", "detail", "description", fallback="No summary available.")),
            }
        )
    return roles or FALLBACK_DATA["roles"]


def load_dashboard_data() -> dict[str, Any]:
    state_data = current_erp_data()
    if ERP_CORE is not None and state_data is not None and callable(getattr(ERP_CORE, "build_dashboard_data", None)):
        base = {**FALLBACK_DATA, **ERP_CORE.build_dashboard_data(state_data), "_seed": state_data}
    elif ERP_CORE is not None:
        base = {**FALLBACK_DATA, **build_seed_dashboard(state_data)} if state_data is not None else dict(FALLBACK_DATA)
    else:
        snapshot = call_first(ERP_CORE, ("get_dashboard_data", "dashboard_data", "get_dashboard", "dashboard"))
        base = {**FALLBACK_DATA, **snapshot} if isinstance(snapshot, dict) else dict(FALLBACK_DATA)

    base["kpis"] = normalize_kpis(base.get("kpis"))
    base["risk_flags"] = normalize_risks(base.get("risk_flags"))
    base["roles"] = normalize_roles(base.get("roles"))
    for key in ("inventory", "sales_orders", "purchase_orders", "invoices", "fulfillment_risks"):
        base[key] = as_list(base.get(key)) or FALLBACK_DATA[key]
    base["audit_log"] = ERP_STATE.load_audit() if ERP_STATE is not None else []

    return base


def health_payload() -> dict[str, Any]:
    return {
        "status": "ok",
        "service": "agentic-erp-system",
        "version": APP_VERSION,
        "llm_enabled": bool(AI_COPILOT and getattr(AI_COPILOT, "llm_enabled", lambda: False)()),
    }


def readiness_payload() -> tuple[int, dict[str, Any]]:
    checks: dict[str, Any] = {
        "erp_core": ERP_CORE is not None,
        "adaptive_erp": ADAPTIVE_ERP is not None,
        "erp_state": ERP_STATE is not None,
    }
    if ERP_STATE is not None:
        checks["state_path"] = str(ERP_STATE.state_path())
        try:
            data = current_erp_data()
            checks["state_loadable"] = data is not None
            checks["audit_loadable"] = isinstance(ERP_STATE.load_audit(), list)
        except Exception as exc:
            checks["state_loadable"] = False
            checks["state_error"] = type(exc).__name__
    ready = all(value for value in checks.values() if isinstance(value, bool))
    payload = {"status": "ready" if ready else "degraded", "checks": checks}
    return (200 if ready else 503), payload


def json_response(payload: dict[str, Any]) -> bytes:
    return (json.dumps(payload, sort_keys=True) + "\n").encode("utf-8")


def run_erp_command(command: str) -> str:
    if ADAPTIVE_ERP is None or ERP_STATE is None:
        return "ERP command engine is unavailable."

    def mutate(data: Any) -> tuple[Any, Any]:
        return ADAPTIVE_ERP.execute_goal(command, data)

    _, result = ERP_STATE.update_data(mutate)
    if result.changed:
        ERP_STATE.append_audit(result.message)
    return result.message


def run_quick_action(params: dict[str, list[str]]) -> str:
    if ERP_CORE is None or ERP_STATE is None:
        return "ERP action engine is unavailable."

    action = params.get("action", [""])[0]
    try:
        if action not in {"create_po", "receive_po", "pay_invoice", "reset"}:
            return "Unknown ERP action."

        def mutate(data: Any) -> tuple[Any, str]:
            if action == "create_po":
                sku = params.get("sku", [""])[0]
                quantity = int(params.get("quantity", ["0"])[0])
                updated, po = ERP_CORE.create_purchase_order(data, sku, quantity)
                return updated, f"Created {po.id} for {sku} with {po.lines[0].quantity} units."
            if action == "receive_po":
                po_id = params.get("po_id", [""])[0]
                updated, po = ERP_CORE.receive_purchase_order(data, po_id)
                return updated, f"Received {po.id}; inventory is updated."
            if action == "pay_invoice":
                invoice_id = params.get("invoice_id", [""])[0]
                updated, invoice = ERP_CORE.apply_invoice_payment(data, invoice_id)
                return updated, f"Recorded payment for {invoice.id}; balance is {invoice.balance_due}."
            return ERP_CORE.seed_erp_data(), "Reset ERP demo data."

        _, message = ERP_STATE.update_data(mutate)
    except (TypeError, ValueError) as exc:
        return str(exc)

    ERP_STATE.append_audit(message)
    return message


def ask_erp(question: str, data: dict[str, Any]) -> str:
    clean_question = question.strip()
    if not clean_question:
        return ""

    seed = data.get("_seed") or seeded_data() or data
    if AI_COPILOT is not None and ERP_CORE is not None:
        answer_question_with_llm = getattr(AI_COPILOT, "answer_question_with_llm", None)
        llm_enabled = getattr(AI_COPILOT, "llm_enabled", None)
        if callable(answer_question_with_llm) and callable(llm_enabled) and llm_enabled():
            try:
                answer = answer_question_with_llm(clean_question, seed, ERP_CORE)
            except Exception as exc:
                rules_answer = AI_COPILOT.answer_question(clean_question, seed, ERP_CORE)
                return f"LLM unavailable ({type(exc).__name__}). Rules answer: {rules_answer}"
            if answer:
                return text(answer)

        answer_question = getattr(AI_COPILOT, "answer_question", None)
        if callable(answer_question):
            answer = answer_question(clean_question, seed, ERP_CORE)
            if answer:
                return text(answer)

    for module in (AI_COPILOT, ERP_CORE):
        if module is None:
            continue
        for name in ("ask_erp", "answer_question", "ask", "respond"):
            func = getattr(module, name, None)
            if not callable(func):
                continue
            for args in ((clean_question, seed, ERP_CORE), (clean_question, seed), (clean_question, data)):
                if not callable_accepts(func, *args):
                    continue
                answer = func(*args)
                if answer:
                    return text(answer)

    overdue = [row for row in data["invoices"] if "overdue" in text(pick(row, "status")).lower()]
    low_stock = [row for row in data["inventory"] if "low" in text(pick(row, "status")).lower()]
    delayed = [row for row in data["purchase_orders"] if "delay" in text(pick(row, "status")).lower()]
    return (
        "Copilot module is not available yet. Current snapshot: "
        f"{len(low_stock)} low-stock inventory item(s), "
        f"{len(delayed)} delayed purchase order(s), and "
        f"{len(overdue)} overdue invoice(s)."
    )


def esc(value: Any) -> str:
    return html.escape(text(value), quote=True)


def render_kpis(kpis: list[dict[str, str]]) -> str:
    return "".join(
        f"""
        <article class="kpi-card">
            <span>{esc(kpi["label"])}</span>
            <strong>{esc(kpi["value"])}</strong>
            <small>{esc(kpi["trend"])}</small>
        </article>
        """
        for kpi in kpis
    )


def render_risks(risks: list[dict[str, str]]) -> str:
    return "".join(
        f"""
        <li class="risk-item">
            <span class="risk-level">{esc(risk["level"])}</span>
            <div>
                <strong>{esc(risk["title"])}</strong>
                <small>{esc(risk["detail"])}</small>
            </div>
        </li>
        """
        for risk in risks
    )


def render_roles(roles: list[dict[str, str]]) -> str:
    return "".join(
        f"""
        <li>
            <strong>{esc(role["role"])}</strong>
            <span>{esc(role["summary"])}</span>
        </li>
        """
        for role in roles
    )


def render_audit(entries: list[dict[str, str]]) -> str:
    if not entries:
        return "<li><span>No workflow activity yet.</span></li>"
    return "".join(
        f"""
        <li>
            <strong>{esc(entry.get("timestamp", ""))}</strong>
            <span>{esc(entry.get("message", ""))}</span>
        </li>
        """
        for entry in entries
    )


def render_quick_actions(erp_data: Any) -> str:
    if erp_data is None or ERP_CORE is None:
        return "<p class=\"muted-copy\">ERP actions are unavailable.</p>"

    recommendation_forms = ""
    if AI_COPILOT is not None:
        for rec in AI_COPILOT.reorder_recommendations(erp_data, ERP_CORE)[:3]:
            recommendation_forms += f"""
            <form method="post" action="/action" class="inline-action">
                <input type="hidden" name="action" value="create_po">
                <input type="hidden" name="sku" value="{esc(rec["sku"])}">
                <input type="hidden" name="quantity" value="{esc(rec["quantity"])}">
                <button type="submit">Create PO for {esc(rec["sku"])} ({esc(rec["quantity"])} units)</button>
            </form>
            """

    receive_forms = "".join(
        f"""
        <form method="post" action="/action" class="inline-action">
            <input type="hidden" name="action" value="receive_po">
            <input type="hidden" name="po_id" value="{esc(po.id)}">
            <button type="submit">Receive {esc(po.id)}</button>
        </form>
        """
        for po in ERP_CORE.delayed_purchase_orders(erp_data)[:2]
    )
    payment_forms = "".join(
        f"""
        <form method="post" action="/action" class="inline-action">
            <input type="hidden" name="action" value="pay_invoice">
            <input type="hidden" name="invoice_id" value="{esc(invoice.id)}">
            <button type="submit">Record payment for {esc(invoice.id)}</button>
        </form>
        """
        for invoice in ERP_CORE.overdue_invoices(erp_data)[:2]
    )
    reset_form = """
        <form method="post" action="/action" class="inline-action reset-action">
            <input type="hidden" name="action" value="reset">
            <button type="submit">Reset demo data</button>
        </form>
    """
    forms = recommendation_forms + receive_forms + payment_forms + reset_form
    return forms or "<p class=\"muted-copy\">No recommended workflow actions right now.</p>"


def render_table(title: str, records: list[Any], columns: tuple[tuple[str, str], ...]) -> str:
    header = "".join(f"<th>{esc(label)}</th>" for _, label in columns)
    rows = []
    for record in records:
        cells = []
        for key, _ in columns:
            value = pick(record, key, fallback="")
            if key in {"total", "amount"}:
                value = money(value)
            elif key == "stock":
                value = number(value)
            cells.append(f"<td>{esc(value)}</td>")
        rows.append(f"<tr>{''.join(cells)}</tr>")
    body = "".join(rows) or f"<tr><td colspan=\"{len(columns)}\">No records available.</td></tr>"
    return f"""
    <section class="table-panel">
        <div class="section-heading">
            <h2>{esc(title)}</h2>
            <span>{len(records)} records</span>
        </div>
        <div class="table-wrap">
            <table>
                <thead><tr>{header}</tr></thead>
                <tbody>{body}</tbody>
            </table>
        </div>
    </section>
    """


def render_page(question: str = "", answer: str = "", notice: str = "") -> bytes:
    data = load_dashboard_data()
    if question and not answer:
        answer = ask_erp(question, data)
    llm_state = "LLM enabled" if AI_COPILOT and getattr(AI_COPILOT, "llm_enabled", lambda: False)() else "rules fallback"
    notice_html = f'<div class="notice">{esc(notice)}</div>' if notice else ""

    html_doc = f"""<!doctype html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>ERP Analytics Demo</title>
    <link rel="stylesheet" href="/static/styles.css">
</head>
<body>
    <header class="topbar">
        <div>
            <p>ERP Analytics Demo</p>
            <h1>Operating Snapshot</h1>
        </div>
        <span class="system-pill">Synthetic sample data | {esc(llm_state)}</span>
    </header>

    <main>
        {notice_html}
        <section class="kpi-grid" aria-label="ERP KPIs">
            {render_kpis(data["kpis"])}
        </section>

        <section class="overview-grid">
            <div class="panel">
                <div class="section-heading">
                    <h2>Risk Flags</h2>
                    <span>Sample review</span>
                </div>
                <ul class="risk-list">{render_risks(data["risk_flags"])}</ul>
            </div>
            <div class="panel">
                <div class="section-heading">
                    <h2>Role Summaries</h2>
                    <span>Today</span>
                </div>
                <ul class="role-list">{render_roles(data["roles"])}</ul>
            </div>
            <form class="ask-panel" method="post" action="/ask">
                <div class="section-heading">
                    <h2>Ask ERP</h2>
                    <span>Copilot</span>
                </div>
                <label for="question">Question</label>
                <textarea id="question" name="question" rows="4" placeholder="What needs attention before close of business?">{esc(question)}</textarea>
                <button type="submit">Ask</button>
                {"<output>" + esc(answer) + "</output>" if answer else ""}
            </form>
        </section>

        <section class="workflow-grid">
            <form class="command-panel" method="post" action="/command">
                <div class="section-heading">
                    <h2>Command ERP</h2>
                    <span>Workflow</span>
                </div>
                <label for="command">Command</label>
                <textarea id="command" name="command" rows="3" placeholder="Try: reorder PUMP-A, receive PO-1001, or mark INV-9001 paid"></textarea>
                <button type="submit">Run Command</button>
            </form>
            <div class="panel">
                <div class="section-heading">
                    <h2>Quick Actions</h2>
                    <span>Suggested</span>
                </div>
                <div class="action-list">{render_quick_actions(data.get("_seed"))}</div>
            </div>
            <div class="panel">
                <div class="section-heading">
                    <h2>Activity</h2>
                    <span>Latest</span>
                </div>
                <ul class="role-list">{render_audit(data.get("audit_log", []))}</ul>
            </div>
        </section>

        <section class="tables-grid">
            {render_table("Fulfillment Risk", data["fulfillment_risks"], (("order_id", "Order"), ("customer", "Customer"), ("sku", "SKU"), ("required", "Required"), ("available", "Available"), ("status", "Status"), ("next_receipt", "Next Receipt")))}
            {render_table("Inventory", data["inventory"], (("sku", "SKU"), ("item", "Item"), ("stock", "Stock"), ("status", "Status")))}
            {render_table("Sales Orders", data["sales_orders"], (("id", "Order"), ("customer", "Customer"), ("total", "Total"), ("status", "Status")))}
            {render_table("Purchase Orders", data["purchase_orders"], (("id", "PO"), ("supplier", "Supplier"), ("total", "Total"), ("status", "Status")))}
            {render_table("Invoices", data["invoices"], (("id", "Invoice"), ("customer", "Customer"), ("amount", "Amount"), ("status", "Status")))}
        </section>
    </main>
</body>
</html>"""
    return html_doc.encode("utf-8")


class ERPRequestHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path == "/" or self.path.startswith("/?"):
            self.respond(200, render_page(), "text/html; charset=utf-8")
            return
        if self.path == "/healthz":
            self.respond(200, json_response(health_payload()), "application/json; charset=utf-8")
            return
        if self.path == "/readyz":
            status, payload = readiness_payload()
            self.respond(status, json_response(payload), "application/json; charset=utf-8")
            return
        if self.path == "/static/styles.css":
            css_path = STATIC_DIR / "styles.css"
            if css_path.exists():
                self.respond(200, css_path.read_bytes(), "text/css; charset=utf-8")
            else:
                self.respond(404, b"Not found", "text/plain; charset=utf-8")
            return
        self.respond(404, b"Not found", "text/plain; charset=utf-8")

    def do_POST(self) -> None:
        if self.path not in {"/ask", "/command", "/action"}:
            self.respond(404, b"Not found", "text/plain; charset=utf-8")
            return
        try:
            length = parse_content_length(self.headers.get("Content-Length", "0"), max_post_body_bytes())
        except RequestTooLarge:
            self.respond(413, b"Request body too large", "text/plain; charset=utf-8")
            return
        except ValueError:
            self.respond(400, b"Invalid Content-Length", "text/plain; charset=utf-8")
            return
        body = self.rfile.read(length).decode("utf-8", errors="replace")
        params = parse_qs(body)
        if self.path == "/ask":
            question = params.get("question", [""])[0]
            self.respond(200, render_page(question=question), "text/html; charset=utf-8")
            return
        if self.path == "/command":
            message = run_erp_command(params.get("command", [""])[0])
            self.respond(200, render_page(notice=message), "text/html; charset=utf-8")
            return
        message = run_quick_action(params)
        self.respond(200, render_page(notice=message), "text/html; charset=utf-8")

    def respond(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: Any) -> None:
        print(f"{self.address_string()} - {format % args}")


def main() -> None:
    host = os.environ.get("HOST", DEFAULT_HOST)
    port = int(os.environ.get("PORT", DEFAULT_PORT))
    server = ThreadingHTTPServer((host, port), ERPRequestHandler)
    print(f"Agentic ERP dashboard running at http://{host}:{port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
