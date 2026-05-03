from concurrent.futures import ThreadPoolExecutor
import http.client
import json
import unittest
import os
from pathlib import Path
import tempfile
import threading
from http.server import ThreadingHTTPServer
from unittest.mock import patch

import app
import erp_state


class LiveERPServer:
    def __enter__(self) -> "LiveERPServer":
        self.server = ThreadingHTTPServer((app.DEFAULT_HOST, 0), app.ERPRequestHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.host, self.port = self.server.server_address
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)

    def request(
        self,
        method: str,
        path: str,
        body: str | None = None,
        headers: dict[str, str] | None = None,
    ) -> tuple[int, str, bytes]:
        connection = http.client.HTTPConnection(self.host, self.port, timeout=5)
        connection.request(method, path, body=body, headers=headers or {})
        response = connection.getresponse()
        payload = response.read()
        content_type = response.getheader("Content-Type", "")
        connection.close()
        return response.status, content_type, payload


class AppHelperTests(unittest.TestCase):
    def test_parse_content_length_rejects_bad_values(self) -> None:
        self.assertEqual(0, app.parse_content_length(None))
        self.assertEqual(12, app.parse_content_length("12"))
        self.assertEqual(12, app.parse_content_length("12", max_length=12))

        with self.assertRaises(ValueError):
            app.parse_content_length("bad")

        with self.assertRaises(ValueError):
            app.parse_content_length("-1")

        with self.assertRaises(app.RequestTooLarge):
            app.parse_content_length("13", max_length=12)

    def test_ask_erp_prefers_core_seed_for_stock_answers(self) -> None:
        with patch.object(app.AI_COPILOT, "llm_enabled", return_value=False):
            answer = app.ask_erp("What stock is at risk?", app.load_dashboard_data())

        self.assertIn("PUMP-A", answer)
        self.assertIn("SENSOR-T", answer)
        self.assertNotIn("BOLT-10", answer)
        self.assertNotIn("VALVE-S", answer)

    def test_command_updates_persistent_erp_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            state_path = Path(tmp) / "erp_state.json"
            audit_path = Path(tmp) / "audit.jsonl"
            with patch.dict(os.environ, {"ERP_STATE_PATH": str(state_path), "ERP_AUDIT_PATH": str(audit_path)}):
                message = app.run_erp_command("receive PO-1001")
                data = erp_state.load_data(state_path)
                po = next(order for order in data.purchase_orders if order.id == "PO-1001")
                audit = erp_state.load_audit(audit_path)

        self.assertIn("Received PO-1001", message)
        self.assertEqual("received", po.status)
        self.assertEqual("Received PO-1001; inventory is updated.", audit[0]["message"])
        self.assertEqual("receive_purchase_order", audit[0]["action"])
        self.assertEqual("success", audit[0]["status"])


class AppHTTPTests(unittest.TestCase):
    def test_health_and_ready_endpoints_return_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            state_path = Path(tmp) / "erp_state.json"
            audit_path = Path(tmp) / "audit.jsonl"
            with patch.dict(os.environ, {"ERP_STATE_PATH": str(state_path), "ERP_AUDIT_PATH": str(audit_path)}):
                with LiveERPServer() as server:
                    health_status, health_type, health_body = server.request("GET", "/healthz")
                    ready_status, ready_type, ready_body = server.request("GET", "/readyz")

        self.assertEqual(200, health_status)
        self.assertIn("application/json", health_type)
        self.assertEqual("ok", json.loads(health_body)["status"])
        self.assertEqual(200, ready_status)
        self.assertIn("application/json", ready_type)
        self.assertEqual("ready", json.loads(ready_body)["status"])

    def test_ready_endpoint_reports_sqlite_storage_probe(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "erp.sqlite3"
            with patch.dict(os.environ, {"ERP_DB_PATH": str(db_path)}, clear=True):
                with LiveERPServer() as server:
                    status, content_type, body = server.request("GET", "/readyz")
            self.assertTrue(db_path.exists())

        payload = json.loads(body)
        self.assertEqual(200, status)
        self.assertIn("application/json", content_type)
        self.assertEqual("ready", payload["status"])
        self.assertEqual("sqlite", payload["checks"]["storage"]["backend"])
        self.assertTrue(payload["checks"]["storage_writeable"])

    def test_static_css_and_not_found_paths(self) -> None:
        with LiveERPServer() as server:
            css_status, css_type, css_body = server.request("GET", "/static/styles.css")
            missing_status, _, missing_body = server.request("GET", "/missing")

        self.assertEqual(200, css_status)
        self.assertIn("text/css", css_type)
        self.assertIn(b":root", css_body)
        self.assertEqual(404, missing_status)
        self.assertEqual(b"Not found", missing_body)

    def test_metrics_endpoint_reports_request_counts(self) -> None:
        before = app.metrics_payload()["requests_total"]
        with LiveERPServer() as server:
            server.request("GET", "/healthz")
            server.request("GET", "/missing")
            status, content_type, body = server.request("GET", "/metrics")

        metrics = json.loads(body)
        self.assertEqual(200, status)
        self.assertIn("application/json", content_type)
        self.assertGreaterEqual(metrics["requests_total"], before + 2)
        self.assertIn("200", metrics["status_counts"])
        self.assertIn("404", metrics["status_counts"])

    def test_post_rejects_oversized_body(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            state_path = Path(tmp) / "erp_state.json"
            audit_path = Path(tmp) / "audit.jsonl"
            env = {
                "ERP_STATE_PATH": str(state_path),
                "ERP_AUDIT_PATH": str(audit_path),
                "MAX_POST_BODY_BYTES": "8",
            }
            with patch.dict(os.environ, env):
                with LiveERPServer() as server:
                    status, content_type, body = server.request(
                        "POST",
                        "/command",
                        body="command=receive+PO-1001",
                        headers={"Content-Type": "application/x-www-form-urlencoded"},
                    )

        self.assertEqual(413, status)
        self.assertIn("text/plain", content_type)
        self.assertEqual(b"Request body too large", body)

    def test_parallel_quick_actions_create_distinct_purchase_orders(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            state_path = Path(tmp) / "erp_state.json"
            audit_path = Path(tmp) / "audit.jsonl"
            env = {"ERP_STATE_PATH": str(state_path), "ERP_AUDIT_PATH": str(audit_path)}
            params = {"action": ["create_po"], "sku": ["PUMP-A"], "quantity": ["1"]}
            with patch.dict(os.environ, env):
                with ThreadPoolExecutor(max_workers=2) as executor:
                    messages = sorted(executor.map(lambda _: app.run_quick_action(params), range(2)))
                data = erp_state.load_data(state_path)

        self.assertEqual(
            ["Created PO-1003 for PUMP-A with 1 units.", "Created PO-1004 for PUMP-A with 1 units."],
            messages,
        )
        self.assertIn("PO-1003", [po.id for po in data.purchase_orders])
        self.assertIn("PO-1004", [po.id for po in data.purchase_orders])

    def test_dashboard_renders_fulfillment_risk_table(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            state_path = Path(tmp) / "erp_state.json"
            audit_path = Path(tmp) / "audit.jsonl"
            env = {"ERP_STATE_PATH": str(state_path), "ERP_AUDIT_PATH": str(audit_path)}
            with patch.dict(os.environ, env):
                html = app.render_page().decode("utf-8")

        self.assertIn("Fulfillment Risk", html)
        self.assertIn("SO-5001", html)
        self.assertIn("PUMP-A", html)
        self.assertIn("AR Aging", html)

    def test_quick_action_accepts_partial_invoice_payment(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            state_path = Path(tmp) / "erp_state.json"
            audit_path = Path(tmp) / "audit.jsonl"
            env = {"ERP_STATE_PATH": str(state_path), "ERP_AUDIT_PATH": str(audit_path)}
            params = {"action": ["pay_invoice"], "invoice_id": ["INV-9001"], "amount": ["500.00"]}
            with patch.dict(os.environ, env):
                message = app.run_quick_action(params)
                data = erp_state.load_data(state_path)
                audit = erp_state.load_audit(audit_path)

        invoice = next(invoice for invoice in data.invoices if invoice.id == "INV-9001")
        self.assertEqual("Recorded payment for INV-9001; balance is 1000.00.", message)
        self.assertEqual("open", invoice.status)
        self.assertEqual("1000.00", str(invoice.balance_due))
        self.assertEqual("pay_invoice", audit[0]["action"])
        self.assertEqual("INV-9001", audit[0]["entity_id"])

    def test_command_preview_does_not_persist_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            state_path = Path(tmp) / "erp_state.json"
            audit_path = Path(tmp) / "audit.jsonl"
            env = {"ERP_STATE_PATH": str(state_path), "ERP_AUDIT_PATH": str(audit_path)}
            with patch.dict(os.environ, env):
                message = app.preview_erp_command("receive PO-1001")
                data = erp_state.load_data(state_path)
                audit_exists = audit_path.exists()

        po = next(order for order in data.purchase_orders if order.id == "PO-1001")
        self.assertIn("Preview: receive PO-1001", message)
        self.assertEqual("open", po.status)
        self.assertFalse(audit_exists)

    def test_command_form_renders_preview_and_run_controls(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            state_path = Path(tmp) / "erp_state.json"
            audit_path = Path(tmp) / "audit.jsonl"
            env = {"ERP_STATE_PATH": str(state_path), "ERP_AUDIT_PATH": str(audit_path)}
            with patch.dict(os.environ, env):
                html = app.render_page().decode("utf-8")

        self.assertIn('value="preview"', html)
        self.assertIn('value="run"', html)

    def test_invalid_quick_action_returns_bad_request_page(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "erp.sqlite3"
            with patch.dict(os.environ, {"ERP_DB_PATH": str(db_path)}, clear=True):
                with LiveERPServer() as server:
                    status, content_type, body = server.request(
                        "POST",
                        "/action",
                        body="action=missing",
                        headers={"Content-Type": "application/x-www-form-urlencoded"},
                    )

        self.assertEqual(400, status)
        self.assertIn("text/html", content_type)
        self.assertIn("Unknown ERP action.", body.decode("utf-8"))

    def test_unknown_command_returns_bad_request_page_without_audit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "erp.sqlite3"
            with patch.dict(os.environ, {"ERP_DB_PATH": str(db_path)}, clear=True):
                with LiveERPServer() as server:
                    status, content_type, body = server.request(
                        "POST",
                        "/command",
                        body="command=make+the+business+better&mode=run",
                        headers={"Content-Type": "application/x-www-form-urlencoded"},
                    )
                audit = erp_state.load_audit(db_path)

        self.assertEqual(400, status)
        self.assertIn("text/html", content_type)
        self.assertIn("Try commands like", body.decode("utf-8"))
        self.assertEqual([], audit)

    def test_api_dashboard_returns_json_contract(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "erp.sqlite3"
            with patch.dict(os.environ, {"ERP_DB_PATH": str(db_path)}, clear=True):
                with LiveERPServer() as server:
                    status, content_type, body = server.request("GET", "/api/v1/dashboard")

        payload = json.loads(body)
        self.assertEqual(200, status)
        self.assertIn("application/json", content_type)
        self.assertTrue(payload["ok"])
        self.assertIsNone(payload["error"])
        self.assertIn("kpis", payload["data"])
        self.assertIn("fulfillment_risks", payload["data"])
        self.assertNotIn("_seed", payload["data"])

    def test_api_command_preview_does_not_mutate_or_audit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "erp.sqlite3"
            with patch.dict(os.environ, {"ERP_DB_PATH": str(db_path)}, clear=True):
                with LiveERPServer() as server:
                    status, content_type, body = server.request(
                        "POST",
                        "/api/v1/command/preview",
                        body=json.dumps({"command": "receive PO-1001"}),
                        headers={"Content-Type": "application/json"},
                    )
                data = erp_state.load_data(db_path)
                audit = erp_state.load_audit(db_path)

        payload = json.loads(body)
        po = next(order for order in data.purchase_orders if order.id == "PO-1001")
        self.assertEqual(200, status)
        self.assertIn("application/json", content_type)
        self.assertTrue(payload["ok"])
        self.assertFalse(payload["data"]["changed"])
        self.assertEqual("open", po.status)
        self.assertEqual([], audit)

    def test_api_command_run_persists_state_and_audit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "erp.sqlite3"
            with patch.dict(os.environ, {"ERP_DB_PATH": str(db_path)}, clear=True):
                with LiveERPServer() as server:
                    status, _, body = server.request(
                        "POST",
                        "/api/v1/command/run",
                        body=json.dumps({"command": "receive PO-1001"}),
                        headers={"Content-Type": "application/json"},
                    )
                data = erp_state.load_data(db_path)
                audit = erp_state.load_audit(db_path)

        payload = json.loads(body)
        po = next(order for order in data.purchase_orders if order.id == "PO-1001")
        self.assertEqual(200, status)
        self.assertTrue(payload["ok"])
        self.assertEqual("received", po.status)
        self.assertEqual("receive_purchase_order", audit[0]["action"])

    def test_api_invalid_action_returns_error_envelope(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "erp.sqlite3"
            with patch.dict(os.environ, {"ERP_DB_PATH": str(db_path)}, clear=True):
                with LiveERPServer() as server:
                    status, content_type, body = server.request(
                        "POST",
                        "/api/v1/actions",
                        body=json.dumps({"action": "missing"}),
                        headers={"Content-Type": "application/json"},
                    )

        payload = json.loads(body)
        self.assertEqual(400, status)
        self.assertIn("application/json", content_type)
        self.assertFalse(payload["ok"])
        self.assertEqual("validation_error", payload["error"]["code"])
        self.assertEqual("Unknown ERP action.", payload["error"]["message"])

    def test_api_rejects_malformed_json(self) -> None:
        with LiveERPServer() as server:
            status, content_type, body = server.request(
                "POST",
                "/api/v1/ask",
                body="{bad json",
                headers={"Content-Type": "application/json"},
            )

        payload = json.loads(body)
        self.assertEqual(400, status)
        self.assertIn("application/json", content_type)
        self.assertFalse(payload["ok"])
        self.assertEqual("bad_json", payload["error"]["code"])


if __name__ == "__main__":
    unittest.main()
