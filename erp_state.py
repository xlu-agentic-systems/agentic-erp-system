"""Local persistence for the ERP demo state."""

from __future__ import annotations

from dataclasses import asdict
from datetime import date, datetime, timezone
from decimal import Decimal
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import threading
from typing import Any, Callable, TypeVar

try:
    import fcntl
except ImportError:  # pragma: no cover - fallback for non-Unix local runs.
    fcntl = None  # type: ignore[assignment]

import erp_core


BASE_DIR = Path(__file__).resolve().parent
DEFAULT_STATE_PATH = BASE_DIR / "data" / "erp_state.json"
DEFAULT_AUDIT_PATH = BASE_DIR / "data" / "audit.jsonl"
DEFAULT_DB_PATH = BASE_DIR / "data" / "erp.sqlite3"
STATE_SCHEMA_VERSION = 1
_LAST_RECOVERY: dict[str, str] | None = None
_PROCESS_LOCK = threading.Lock()
T = TypeVar("T")


def state_path() -> Path:
    return Path(os.environ.get("ERP_STATE_PATH", DEFAULT_STATE_PATH))


def audit_path() -> Path:
    return Path(os.environ.get("ERP_AUDIT_PATH", DEFAULT_AUDIT_PATH))


def db_path() -> Path:
    return Path(os.environ.get("ERP_DB_PATH", DEFAULT_DB_PATH))


def storage_backend() -> str:
    backend = os.environ.get("ERP_STORAGE_BACKEND", "").strip().lower()
    if backend in {"sqlite", "json"}:
        return backend
    if os.environ.get("ERP_DB_PATH"):
        return "sqlite"
    if os.environ.get("ERP_STATE_PATH"):
        return "json"
    return "sqlite"


def last_recovery() -> dict[str, str] | None:
    return dict(_LAST_RECOVERY) if _LAST_RECOVERY is not None else None


def load_data(path: str | Path | None = None) -> erp_core.ERPData:
    if _should_use_sqlite(path):
        return _load_data_sqlite(_resolved_db_path(path))
    return _load_data_json(path)


def save_data(data: erp_core.ERPData, path: str | Path | None = None) -> None:
    if _should_use_sqlite(path):
        _save_data_sqlite(data, _resolved_db_path(path))
        return
    _save_data_json(data, path)


def reset_data(path: str | Path | None = None) -> erp_core.ERPData:
    data = erp_core.seed_erp_data()
    save_data(data, path)
    return data


def update_data(
    mutator: Callable[[erp_core.ERPData], tuple[erp_core.ERPData, T]],
    path: str | Path | None = None,
) -> tuple[erp_core.ERPData, T]:
    if _should_use_sqlite(path):
        return _update_data_sqlite(mutator, _resolved_db_path(path))
    return _update_data_json(mutator, path)


def update_data_with_audit(
    mutator: Callable[[erp_core.ERPData], tuple[erp_core.ERPData, T]],
    audit_message: Callable[[T], str | None],
    path: str | Path | None = None,
) -> tuple[erp_core.ERPData, T]:
    if _should_use_sqlite(path) and _should_use_sqlite_audit(path):
        return _update_data_sqlite(mutator, _resolved_db_path(path), audit_message)
    if _should_use_sqlite(path):
        updated, result = _update_data_sqlite(mutator, _resolved_db_path(path))
        message = audit_message(result)
        if message:
            append_audit(message)
        return updated, result
    return _update_data_json(mutator, path, audit_message)


def append_audit(message: str, path: str | Path | None = None) -> None:
    if _should_use_sqlite_audit(path):
        _append_audit_sqlite(message, _resolved_db_path(path))
        return
    _append_audit_json(message, path)


def load_audit(path: str | Path | None = None, limit: int = 8) -> list[dict[str, str]]:
    if _should_use_sqlite_audit(path):
        return _load_audit_sqlite(_resolved_db_path(path), limit)
    return _load_audit_json(path, limit)


def storage_status(write_probe: bool = False) -> dict[str, Any]:
    backend = storage_backend()
    if backend == "sqlite":
        return _sqlite_storage_status(write_probe)
    return _json_storage_status(write_probe)


def _load_data_json(path: str | Path | None = None) -> erp_core.ERPData:
    global _LAST_RECOVERY
    target = Path(path) if path is not None else state_path()
    if not target.exists():
        return erp_core.seed_erp_data()
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
        return _erp_data_from_dict(_state_data_payload(payload))
    except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        backup_path = _quarantine_state(target)
        _LAST_RECOVERY = {
            "path": str(target),
            "backup_path": str(backup_path),
            "reason": type(exc).__name__,
        }
        return erp_core.seed_erp_data()


def _save_data_json(data: erp_core.ERPData, path: str | Path | None = None) -> None:
    target = Path(path) if path is not None else state_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": STATE_SCHEMA_VERSION,
        "data": _jsonable(asdict(data)),
    }
    _atomic_write_text(target, json.dumps(payload, indent=2, sort_keys=True) + "\n")


def _update_data_json(
    mutator: Callable[[erp_core.ERPData], tuple[erp_core.ERPData, T]],
    path: str | Path | None = None,
    audit_message: Callable[[T], str | None] | None = None,
) -> tuple[erp_core.ERPData, T]:
    target = Path(path) if path is not None else state_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    lock_path = target.with_name(f"{target.name}.lock")
    with _PROCESS_LOCK:
        with lock_path.open("a", encoding="utf-8") as lock_handle:
            _lock_file(lock_handle)
            try:
                current = load_data(target)
                updated, result = mutator(current)
                if updated is not current:
                    save_data(updated, target)
                if audit_message is not None:
                    message = audit_message(result)
                    if message:
                        _append_audit_json(message)
                return updated, result
            finally:
                _unlock_file(lock_handle)


def _append_audit_json(message: str, path: str | Path | None = None) -> None:
    target = Path(path) if path is not None else audit_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    entry = {"timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"), "message": message}
    with target.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, sort_keys=True) + "\n")


def _load_audit_json(path: str | Path | None = None, limit: int = 8) -> list[dict[str, str]]:
    target = Path(path) if path is not None else audit_path()
    if not target.exists():
        return []
    entries = []
    for line in target.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(entry, dict) and "message" in entry:
            entries.append(entry)
    return list(reversed(entries[-limit:]))


def _should_use_sqlite(path: str | Path | None) -> bool:
    if path is not None:
        return _looks_like_sqlite_path(Path(path))
    return storage_backend() == "sqlite"


def _should_use_sqlite_audit(path: str | Path | None) -> bool:
    if path is not None:
        return _looks_like_sqlite_path(Path(path))
    if os.environ.get("ERP_AUDIT_PATH"):
        return False
    return storage_backend() == "sqlite"


def _looks_like_sqlite_path(path: Path) -> bool:
    return path.suffix.lower() in {".db", ".sqlite", ".sqlite3"}


def _resolved_db_path(path: str | Path | None) -> Path:
    if path is not None:
        return Path(path)
    return db_path()


def _connect_sqlite(target: Path) -> sqlite3.Connection:
    target.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(target, timeout=30)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA journal_mode = WAL")
    return connection


def _ensure_sqlite_schema(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS erp_state (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            schema_version INTEGER NOT NULL,
            payload TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            message TEXT NOT NULL
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS storage_metadata (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    connection.commit()


def _load_data_sqlite(path: Path) -> erp_core.ERPData:
    with _connect_sqlite(path) as connection:
        _ensure_sqlite_schema(connection)
        data = _read_sqlite_data(connection)
        if data is None:
            data = erp_core.seed_erp_data()
            _write_sqlite_data(connection, data)
            connection.commit()
        return data


def _save_data_sqlite(data: erp_core.ERPData, path: Path) -> None:
    with _connect_sqlite(path) as connection:
        _ensure_sqlite_schema(connection)
        _write_sqlite_data(connection, data)
        connection.commit()


def _update_data_sqlite(
    mutator: Callable[[erp_core.ERPData], tuple[erp_core.ERPData, T]],
    path: Path,
    audit_message: Callable[[T], str | None] | None = None,
) -> tuple[erp_core.ERPData, T]:
    with _PROCESS_LOCK:
        with _connect_sqlite(path) as connection:
            _ensure_sqlite_schema(connection)
            connection.execute("BEGIN IMMEDIATE")
            try:
                current = _read_sqlite_data(connection) or erp_core.seed_erp_data()
                updated, result = mutator(current)
                if updated is not current:
                    _write_sqlite_data(connection, updated)
                if audit_message is not None:
                    message = audit_message(result)
                    if message:
                        _insert_audit_sqlite(connection, message)
                connection.commit()
                return updated, result
            except Exception:
                connection.rollback()
                raise


def _append_audit_sqlite(message: str, path: Path) -> None:
    with _connect_sqlite(path) as connection:
        _ensure_sqlite_schema(connection)
        _insert_audit_sqlite(connection, message)
        connection.commit()


def _insert_audit_sqlite(connection: sqlite3.Connection, message: str) -> None:
    connection.execute(
        "INSERT INTO audit_log (timestamp, message) VALUES (?, ?)",
        (datetime.now(timezone.utc).isoformat(timespec="seconds"), message),
    )


def _load_audit_sqlite(path: Path, limit: int = 8) -> list[dict[str, str]]:
    with _connect_sqlite(path) as connection:
        _ensure_sqlite_schema(connection)
        rows = connection.execute(
            """
            SELECT timestamp, message
            FROM audit_log
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [{"timestamp": row["timestamp"], "message": row["message"]} for row in rows]


def _read_sqlite_data(connection: sqlite3.Connection) -> erp_core.ERPData | None:
    row = connection.execute(
        "SELECT schema_version, payload FROM erp_state WHERE id = 1"
    ).fetchone()
    if row is None:
        return None
    if int(row["schema_version"]) != STATE_SCHEMA_VERSION:
        raise ValueError("unsupported state schema version")
    payload = json.loads(row["payload"])
    if not isinstance(payload, dict):
        raise ValueError("state data must be a JSON object")
    return _erp_data_from_dict(payload)


def _write_sqlite_data(connection: sqlite3.Connection, data: erp_core.ERPData) -> None:
    connection.execute(
        """
        INSERT INTO erp_state (id, schema_version, payload, updated_at)
        VALUES (1, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            schema_version = excluded.schema_version,
            payload = excluded.payload,
            updated_at = excluded.updated_at
        """,
        (
            STATE_SCHEMA_VERSION,
            json.dumps(_jsonable(asdict(data)), sort_keys=True),
            datetime.now(timezone.utc).isoformat(timespec="seconds"),
        ),
    )


def _sqlite_storage_status(write_probe: bool) -> dict[str, Any]:
    target = db_path()
    status: dict[str, Any] = {
        "backend": "sqlite",
        "db_path": str(target),
        "schema_version": STATE_SCHEMA_VERSION,
        "state_loadable": False,
        "audit_loadable": False,
        "writeable": False,
    }
    try:
        with _connect_sqlite(target) as connection:
            _ensure_sqlite_schema(connection)
            _read_sqlite_data(connection)
            status["state_loadable"] = True
            connection.execute("SELECT COUNT(*) FROM audit_log").fetchone()
            status["audit_loadable"] = True
            if write_probe:
                timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
                connection.execute("BEGIN IMMEDIATE")
                connection.execute(
                    """
                    INSERT INTO storage_metadata (key, value, updated_at)
                    VALUES ('readiness_probe', 'ok', ?)
                    ON CONFLICT(key) DO UPDATE SET
                        value = excluded.value,
                        updated_at = excluded.updated_at
                    """,
                    (timestamp,),
                )
                connection.commit()
            status["writeable"] = True
    except Exception as exc:
        status["error"] = type(exc).__name__
    return status


def _json_storage_status(write_probe: bool) -> dict[str, Any]:
    target = state_path()
    audit = audit_path()
    status: dict[str, Any] = {
        "backend": "json",
        "state_path": str(target),
        "audit_path": str(audit),
        "schema_version": STATE_SCHEMA_VERSION,
        "state_loadable": False,
        "audit_loadable": False,
        "writeable": False,
    }
    try:
        load_data(target)
        status["state_loadable"] = True
        status["audit_loadable"] = isinstance(load_audit(audit), list)
        if write_probe:
            target.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=target.parent, delete=True) as handle:
                handle.write("ok")
                handle.flush()
                os.fsync(handle.fileno())
        status["writeable"] = True
    except Exception as exc:
        status["error"] = type(exc).__name__
    return status


def _state_data_payload(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("state payload must be a JSON object")
    if "data" not in payload:
        return payload
    if payload.get("schema_version") != STATE_SCHEMA_VERSION:
        raise ValueError("unsupported state schema version")
    data = payload["data"]
    if not isinstance(data, dict):
        raise ValueError("state data must be a JSON object")
    return data


def _atomic_write_text(target: Path, content: str) -> None:
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=target.parent,
            prefix=f".{target.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temp_path = Path(handle.name)
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, target)
    finally:
        if temp_path is not None and temp_path.exists():
            temp_path.unlink()


def _quarantine_state(target: Path) -> Path:
    base_name = f"{target.name}.corrupt-{_utc_file_stamp()}"
    for index in range(1000):
        candidate = target.with_name(base_name if index == 0 else f"{base_name}-{index}")
        if not candidate.exists():
            os.replace(target, candidate)
            return candidate
    raise RuntimeError(f"Could not allocate corrupt-state backup path for {target}")


def _utc_file_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _lock_file(handle: Any) -> None:
    if fcntl is not None:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)


def _unlock_file(handle: Any) -> None:
    if fcntl is not None:
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


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
