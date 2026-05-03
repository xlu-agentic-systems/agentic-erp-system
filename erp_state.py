"""Local JSON persistence for the ERP demo state."""

from __future__ import annotations

from dataclasses import asdict
from datetime import date, datetime
from decimal import Decimal
import json
import os
from pathlib import Path
from typing import Any

import erp_core


BASE_DIR = Path(__file__).resolve().parent
DEFAULT_STATE_PATH = BASE_DIR / "data" / "erp_state.json"
DEFAULT_AUDIT_PATH = BASE_DIR / "data" / "audit.jsonl"


def state_path() -> Path:
    return Path(os.environ.get("ERP_STATE_PATH", DEFAULT_STATE_PATH))


def audit_path() -> Path:
    return Path(os.environ.get("ERP_AUDIT_PATH", DEFAULT_AUDIT_PATH))


def load_data(path: str | Path | None = None) -> erp_core.ERPData:
    target = Path(path) if path is not None else state_path()
    if not target.exists():
        return erp_core.seed_erp_data()
    payload = json.loads(target.read_text(encoding="utf-8"))
    return _erp_data_from_dict(payload)


def save_data(data: erp_core.ERPData, path: str | Path | None = None) -> None:
    target = Path(path) if path is not None else state_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(_jsonable(asdict(data)), indent=2, sort_keys=True) + "\n", encoding="utf-8")


def reset_data(path: str | Path | None = None) -> erp_core.ERPData:
    data = erp_core.seed_erp_data()
    save_data(data, path)
    return data


def append_audit(message: str, path: str | Path | None = None) -> None:
    target = Path(path) if path is not None else audit_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    entry = {"timestamp": datetime.now().isoformat(timespec="seconds"), "message": message}
    with target.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, sort_keys=True) + "\n")


def load_audit(path: str | Path | None = None, limit: int = 8) -> list[dict[str, str]]:
    target = Path(path) if path is not None else audit_path()
    if not target.exists():
        return []
    entries = [json.loads(line) for line in target.read_text(encoding="utf-8").splitlines() if line.strip()]
    return list(reversed(entries[-limit:]))


def _jsonable(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, tuple):
        return [_jsonable(item) for item in value]
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {key: _jsonable(item) for key, item in value.items()}
    return value


def _erp_data_from_dict(payload: dict[str, Any]) -> erp_core.ERPData:
    return erp_core.ERPData(
        products=tuple(erp_core.Product(**_with_money(item, "unit_cost", "unit_price")) for item in payload["products"]),
        vendors=tuple(erp_core.Vendor(**_tuple_field(item, "supplied_skus")) for item in payload["vendors"]),
        customers=tuple(erp_core.Customer(**item) for item in payload["customers"]),
        inventory=tuple(erp_core.InventoryItem(**item) for item in payload["inventory"]),
        purchase_orders=tuple(_purchase_order_from_dict(item) for item in payload["purchase_orders"]),
        sales_orders=tuple(_sales_order_from_dict(item) for item in payload["sales_orders"]),
        invoices=tuple(erp_core.Invoice(**_with_money(_with_dates(item, "invoice_date", "due_date"), "amount", "amount_paid")) for item in payload["invoices"]),
        current_cash=erp_core.money(payload["current_cash"]),
    )


def _purchase_order_from_dict(payload: dict[str, Any]) -> erp_core.PurchaseOrder:
    item = _with_dates(payload, "order_date", "expected_date")
    return erp_core.PurchaseOrder(
        id=item["id"],
        vendor_id=item["vendor_id"],
        order_date=item["order_date"],
        expected_date=item["expected_date"],
        status=item["status"],
        lines=tuple(_order_line_from_dict(line) for line in item["lines"]),
    )


def _sales_order_from_dict(payload: dict[str, Any]) -> erp_core.SalesOrder:
    item = _with_dates(payload, "order_date", "requested_ship_date")
    return erp_core.SalesOrder(
        id=item["id"],
        customer_id=item["customer_id"],
        order_date=item["order_date"],
        requested_ship_date=item["requested_ship_date"],
        status=item["status"],
        lines=tuple(_order_line_from_dict(line) for line in item["lines"]),
    )


def _order_line_from_dict(payload: dict[str, Any]) -> erp_core.OrderLine:
    return erp_core.OrderLine(
        product_id=payload["product_id"],
        quantity=int(payload["quantity"]),
        unit_price=erp_core.money(payload["unit_price"]),
    )


def _with_money(payload: dict[str, Any], *fields: str) -> dict[str, Any]:
    item = dict(payload)
    for field in fields:
        item[field] = erp_core.money(item[field])
    return item


def _with_dates(payload: dict[str, Any], *fields: str) -> dict[str, Any]:
    item = dict(payload)
    for field in fields:
        item[field] = date.fromisoformat(item[field])
    return item


def _tuple_field(payload: dict[str, Any], field: str) -> dict[str, Any]:
    item = dict(payload)
    item[field] = tuple(item.get(field, ()))
    return item
