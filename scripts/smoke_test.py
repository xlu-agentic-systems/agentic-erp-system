#!/usr/bin/env python3
"""Dependency-free ERP app smoke test."""

from __future__ import annotations

import http.client
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
from http.server import ThreadingHTTPServer
from urllib.parse import urlencode


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import app  # noqa: E402
import erp_state  # noqa: E402


def request(
    host: str,
    port: int,
    method: str,
    path: str,
    body: str | None = None,
    headers: dict[str, str] | None = None,
) -> tuple[int, str, bytes]:
    connection = http.client.HTTPConnection(host, port, timeout=5)
    connection.request(method, path, body=body, headers=headers or {})
    response = connection.getresponse()
    payload = response.read()
    content_type = response.getheader("Content-Type", "")
    connection.close()
    return response.status, content_type, payload


def assert_status(status: int, expected: int, path: str) -> None:
    if status != expected:
        raise AssertionError(f"{path} returned {status}, expected {expected}")


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "erp.sqlite3"
        backup_path = Path(tmp) / "erp.backup.sqlite3"
        os.environ.pop("ERP_STATE_PATH", None)
        os.environ.pop("ERP_AUDIT_PATH", None)
        os.environ.pop("ERP_STORAGE_BACKEND", None)
        os.environ["ERP_DB_PATH"] = str(db_path)

        server = ThreadingHTTPServer((app.DEFAULT_HOST, 0), app.ERPRequestHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        host, port = server.server_address

        try:
            status, _, health_body = request(host, port, "GET", "/healthz")
            assert_status(status, 200, "/healthz")
            if json.loads(health_body)["status"] != "ok":
                raise AssertionError("/healthz did not report ok")

            status, _, ready_body = request(host, port, "GET", "/readyz")
            assert_status(status, 200, "/readyz")
            if json.loads(ready_body)["status"] != "ready":
                raise AssertionError("/readyz did not report ready")

            form_headers = {"Content-Type": "application/x-www-form-urlencoded"}
            preview_body = urlencode({"command": "receive PO-1001", "mode": "preview"})
            status, _, body = request(host, port, "POST", "/command", preview_body, form_headers)
            assert_status(status, 200, "/command preview")
            if b"Preview: receive PO-1001" not in body:
                raise AssertionError("preview response did not describe PO receipt")

            preview_data = erp_state.load_data(db_path)
            preview_po = next(po for po in preview_data.purchase_orders if po.id == "PO-1001")
            if preview_po.status != "open":
                raise AssertionError("preview mutated purchase order state")

            run_body = urlencode({"command": "receive PO-1001", "mode": "run"})
            status, _, body = request(host, port, "POST", "/command", run_body, form_headers)
            assert_status(status, 200, "/command run")
            if b"Received PO-1001" not in body:
                raise AssertionError("run response did not confirm PO receipt")

            updated = erp_state.load_data(db_path)
            received = next(po for po in updated.purchase_orders if po.id == "PO-1001")
            if received.status != "received":
                raise AssertionError("run command did not persist received PO")
            if not erp_state.load_audit(db_path):
                raise AssertionError("run command did not write audit entry")

            erp_state.backup_sqlite(backup_path, db_path)
            backup = erp_state.load_data(backup_path)
            backup_received = next(po for po in backup.purchase_orders if po.id == "PO-1001")
            if backup_received.status != "received":
                raise AssertionError("SQLite backup did not preserve received PO")
            if not erp_state.load_audit(backup_path):
                raise AssertionError("SQLite backup did not preserve audit rows")

            status, _, metrics_body = request(host, port, "GET", "/metrics")
            assert_status(status, 200, "/metrics")
            if json.loads(metrics_body)["requests_total"] < 4:
                raise AssertionError("/metrics request count is too low")
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

    print("ERP smoke test passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
