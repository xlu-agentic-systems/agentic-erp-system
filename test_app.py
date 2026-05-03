import unittest
import os
from pathlib import Path
import tempfile
from unittest.mock import patch

import app
import erp_state


class AppHelperTests(unittest.TestCase):
    def test_parse_content_length_rejects_bad_values(self) -> None:
        self.assertEqual(0, app.parse_content_length(None))
        self.assertEqual(12, app.parse_content_length("12"))

        with self.assertRaises(ValueError):
            app.parse_content_length("bad")

        with self.assertRaises(ValueError):
            app.parse_content_length("-1")

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


if __name__ == "__main__":
    unittest.main()
