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

    def test_static_css_and_not_found_paths(self) -> None:
        with LiveERPServer() as server:
            css_status, css_type, css_body = server.request("GET", "/static/styles.css")
            missing_status, _, missing_body = server.request("GET", "/missing")

        self.assertEqual(200, css_status)
        self.assertIn("text/css", css_type)
        self.assertIn(b":root", css_body)
        self.assertEqual(404, missing_status)
        self.assertEqual(b"Not found", missing_body)

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


if __name__ == "__main__":
    unittest.main()
