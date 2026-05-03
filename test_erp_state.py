from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from datetime import date
import json
from pathlib import Path
import tempfile
import time
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
            raw_payload = json.loads(state_path.read_text(encoding="utf-8"))

        received = next(po for po in loaded.purchase_orders if po.id == "PO-1001")
        pump_inventory = next(item for item in loaded.inventory if item.product_id == "P-200")
        self.assertEqual(erp_state.STATE_SCHEMA_VERSION, raw_payload["schema_version"])
        self.assertIn("data", raw_payload)
        self.assertEqual("received", received.status)
        self.assertEqual(26, pump_inventory.quantity_on_hand)

    def test_audit_log_round_trips_messages(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            audit_path = Path(tmp) / "audit.jsonl"
            erp_state.append_audit("Created PO-1003", audit_path)
            with audit_path.open("a", encoding="utf-8") as handle:
                handle.write("{partial json\n")
            erp_state.append_audit("Received PO-1001", audit_path)

            messages = erp_state.load_audit(audit_path)
            raw_first_line = json.loads(audit_path.read_text(encoding="utf-8").splitlines()[0])

        self.assertEqual(["Received PO-1001", "Created PO-1003"], [entry["message"] for entry in messages])
        self.assertTrue(raw_first_line["timestamp"].endswith("+00:00"))

    def test_corrupt_state_is_quarantined_and_seed_data_is_loaded(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            state_path = Path(tmp) / "erp_state.json"
            state_path.write_text('{"products": [', encoding="utf-8")

            loaded = erp_state.load_data(state_path)
            backups = list(Path(tmp).glob("erp_state.json.corrupt-*"))
            recovery = erp_state.last_recovery()

        self.assertEqual("PUMP-A", loaded.products[1].sku)
        self.assertEqual(1, len(backups))
        self.assertIsNotNone(recovery)
        self.assertEqual(str(backups[0]), recovery["backup_path"])

    def test_legacy_state_payload_still_loads(self) -> None:
        data = erp_core.seed_erp_data(date(2026, 5, 2))
        with tempfile.TemporaryDirectory() as tmp:
            state_path = Path(tmp) / "erp_state.json"
            state_path.write_text(json.dumps(erp_state._jsonable(asdict(data))), encoding="utf-8")

            loaded = erp_state.load_data(state_path)

        self.assertEqual(data.current_cash, loaded.current_cash)

    def test_update_data_serializes_concurrent_document_creation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            state_path = Path(tmp) / "erp_state.json"
            erp_state.reset_data(state_path)

            def create_purchase_order(_: int) -> str:
                def mutate(data: erp_core.ERPData) -> tuple[erp_core.ERPData, str]:
                    updated, po = erp_core.create_purchase_order(data, "PUMP-A", 1)
                    time.sleep(0.01)
                    return updated, po.id

                _, po_id = erp_state.update_data(mutate, state_path)
                return po_id

            with ThreadPoolExecutor(max_workers=2) as executor:
                returned_ids = sorted(executor.map(create_purchase_order, range(2)))

            persisted_ids = [po.id for po in erp_state.load_data(state_path).purchase_orders]

        self.assertEqual(["PO-1003", "PO-1004"], returned_ids)
        self.assertIn("PO-1003", persisted_ids)
        self.assertIn("PO-1004", persisted_ids)


if __name__ == "__main__":
    unittest.main()
