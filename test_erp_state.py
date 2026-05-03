from datetime import date
from pathlib import Path
import tempfile
import unittest

import adaptive_erp
import erp_core
import erp_state


class ERPStatePersistenceTests(unittest.TestCase):
    def test_save_and_load_round_trips_updated_erp_data(self) -> None:
        data = erp_core.seed_erp_data(date(2026, 5, 2))
        updated, result = adaptive_erp.execute_goal("receive PO-1001", data, date(2026, 5, 2))
        self.assertTrue(result.success)

        with tempfile.TemporaryDirectory() as tmp:
            state_path = Path(tmp) / "erp_state.json"
            erp_state.save_data(updated, state_path)
            loaded = erp_state.load_data(state_path)

        received = next(po for po in loaded.purchase_orders if po.id == "PO-1001")
        pump_inventory = next(item for item in loaded.inventory if item.product_id == "P-200")
        self.assertEqual("received", received.status)
        self.assertEqual(26, pump_inventory.quantity_on_hand)

    def test_audit_log_round_trips_messages(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            audit_path = Path(tmp) / "audit.jsonl"
            erp_state.append_audit("Created PO-1003", audit_path)
            erp_state.append_audit("Received PO-1001", audit_path)

            messages = erp_state.load_audit(audit_path)

        self.assertEqual(["Received PO-1001", "Created PO-1003"], [entry["message"] for entry in messages])


if __name__ == "__main__":
    unittest.main()
