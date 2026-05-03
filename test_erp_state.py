from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from datetime import date
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import time
import unittest
from unittest.mock import patch

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
            erp_state.append_audit("Created PO-1003", audit_path, action="create_po", entity_id="PO-1003")
            with audit_path.open("a", encoding="utf-8") as handle:
                handle.write("{partial json\n")
            erp_state.append_audit("Received PO-1001", audit_path)

            messages = erp_state.load_audit(audit_path)
            raw_first_line = json.loads(audit_path.read_text(encoding="utf-8").splitlines()[0])

        self.assertEqual(["Received PO-1001", "Created PO-1003"], [entry["message"] for entry in messages])
        self.assertEqual("create_po", messages[1]["action"])
        self.assertEqual("PO-1003", messages[1]["entity_id"])
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

    def test_sqlite_save_load_and_audit_round_trip(self) -> None:
        data = erp_core.seed_erp_data(date(2026, 5, 2))
        updated, result = adaptive_erp.execute_goal("receive PO-1001", data, date(2026, 5, 2))
        self.assertTrue(result.success)

        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "erp.sqlite3"
            erp_state.save_data(updated, db_path)
            erp_state.append_audit(result.message, db_path)

            loaded = erp_state.load_data(db_path)
            audit = erp_state.load_audit(db_path)

        received = next(po for po in loaded.purchase_orders if po.id == "PO-1001")
        pump_inventory = next(item for item in loaded.inventory if item.product_id == "P-200")
        self.assertEqual("received", received.status)
        self.assertEqual(26, pump_inventory.quantity_on_hand)
        self.assertEqual(["Received PO-1001; inventory is updated."], [entry["message"] for entry in audit])

    def test_sqlite_audit_records_structured_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "erp.sqlite3"
            erp_state.append_audit(
                "Created PO-1003",
                db_path,
                action="create_po",
                entity_id="PO-1003",
                status="success",
            )

            audit = erp_state.load_audit(db_path)

        self.assertEqual("Created PO-1003", audit[0]["message"])
        self.assertEqual("create_po", audit[0]["action"])
        self.assertEqual("PO-1003", audit[0]["entity_id"])
        self.assertEqual("success", audit[0]["status"])

    def test_sqlite_audit_schema_migrates_message_only_table(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "erp.sqlite3"
            with sqlite3.connect(db_path) as connection:
                connection.execute(
                    """
                    CREATE TABLE audit_log (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        timestamp TEXT NOT NULL,
                        message TEXT NOT NULL
                    )
                    """
                )

            erp_state.append_audit("Legacy compatible", db_path)
            audit = erp_state.load_audit(db_path)

        self.assertEqual("Legacy compatible", audit[0]["message"])
        self.assertEqual("", audit[0]["action"])
        self.assertEqual("", audit[0]["entity_id"])
        self.assertEqual("success", audit[0]["status"])

    def test_sqlite_backup_preserves_state_and_audit_rows(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "erp.sqlite3"
            backup_path = Path(tmp) / "erp.backup.sqlite3"
            erp_state.reset_data(db_path)

            def mutate(data: erp_core.ERPData) -> tuple[erp_core.ERPData, str]:
                updated, po = erp_core.receive_purchase_order(data, "PO-1001")
                return updated, f"Received {po.id}"

            erp_state.update_data_with_audit(
                mutate,
                lambda message: {"message": message, "action": "receive_po", "entity_id": "PO-1001"},
                db_path,
            )

            returned_path = erp_state.backup_sqlite(backup_path, db_path)
            loaded = erp_state.load_data(backup_path)
            audit = erp_state.load_audit(backup_path)

        received = next(po for po in loaded.purchase_orders if po.id == "PO-1001")
        self.assertEqual(backup_path, returned_path)
        self.assertEqual("received", received.status)
        self.assertEqual("Received PO-1001", audit[0]["message"])
        self.assertEqual("receive_po", audit[0]["action"])

    def test_sqlite_backup_rejects_source_path_as_destination(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "erp.sqlite3"
            erp_state.reset_data(db_path)

            with self.assertRaises(ValueError):
                erp_state.backup_sqlite(db_path, db_path)

    def test_sqlite_update_data_serializes_concurrent_document_creation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "erp.sqlite3"
            erp_state.reset_data(db_path)

            def create_purchase_order(_: int) -> str:
                def mutate(data: erp_core.ERPData) -> tuple[erp_core.ERPData, str]:
                    updated, po = erp_core.create_purchase_order(data, "PUMP-A", 1)
                    time.sleep(0.01)
                    return updated, po.id

                _, po_id = erp_state.update_data(mutate, db_path)
                return po_id

            with ThreadPoolExecutor(max_workers=2) as executor:
                returned_ids = sorted(executor.map(create_purchase_order, range(2)))

            persisted_ids = [po.id for po in erp_state.load_data(db_path).purchase_orders]

        self.assertEqual(["PO-1003", "PO-1004"], returned_ids)
        self.assertIn("PO-1003", persisted_ids)
        self.assertIn("PO-1004", persisted_ids)

    def test_sqlite_storage_status_runs_write_probe(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "erp.sqlite3"
            with patch.dict(os.environ, {"ERP_DB_PATH": str(db_path)}, clear=False):
                status = erp_state.storage_status(write_probe=True)

        self.assertEqual("sqlite", status["backend"])
        self.assertEqual(str(db_path), status["db_path"])
        self.assertTrue(status["state_loadable"])
        self.assertTrue(status["audit_loadable"])
        self.assertTrue(status["writeable"])
        self.assertNotIn("error", status)

    def test_sqlite_update_with_audit_rolls_back_when_audit_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "erp.sqlite3"
            erp_state.reset_data(db_path)

            def mutate(data: erp_core.ERPData) -> tuple[erp_core.ERPData, str]:
                updated, po = erp_core.receive_purchase_order(data, "PO-1001")
                return updated, f"Received {po.id}"

            def fail_audit(_: str) -> str:
                raise RuntimeError("audit unavailable")

            with self.assertRaises(RuntimeError):
                erp_state.update_data_with_audit(mutate, fail_audit, db_path)

            loaded = erp_state.load_data(db_path)
            audit = erp_state.load_audit(db_path)

        po = next(order for order in loaded.purchase_orders if order.id == "PO-1001")
        inventory = next(item for item in loaded.inventory if item.product_id == "P-200")
        self.assertEqual("open", po.status)
        self.assertEqual(14, inventory.quantity_on_hand)
        self.assertEqual([], audit)

    def test_concurrent_sqlite_receive_same_purchase_order_only_posts_once(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "erp.sqlite3"
            erp_state.reset_data(db_path)

            def receive(_: int) -> str:
                def mutate(data: erp_core.ERPData) -> tuple[erp_core.ERPData, str]:
                    updated, po = erp_core.receive_purchase_order(data, "PO-1001")
                    time.sleep(0.01)
                    return updated, f"Received {po.id}"

                try:
                    _, message = erp_state.update_data_with_audit(mutate, lambda item: item, db_path)
                    return message
                except ValueError as exc:
                    return str(exc)

            with ThreadPoolExecutor(max_workers=2) as executor:
                messages = sorted(executor.map(receive, range(2)))

            loaded = erp_state.load_data(db_path)
            audit = erp_state.load_audit(db_path)

        received = next(po for po in loaded.purchase_orders if po.id == "PO-1001")
        inventory = next(item for item in loaded.inventory if item.product_id == "P-200")
        self.assertEqual(["PO-1001 is already received", "Received PO-1001"], messages)
        self.assertEqual("received", received.status)
        self.assertEqual(26, inventory.quantity_on_hand)
        self.assertEqual(["Received PO-1001"], [entry["message"] for entry in audit])

    def test_concurrent_sqlite_invoice_payments_cannot_overpay(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "erp.sqlite3"
            erp_state.reset_data(db_path)

            def pay(_: int) -> str:
                def mutate(data: erp_core.ERPData) -> tuple[erp_core.ERPData, str]:
                    updated, invoice = erp_core.apply_invoice_payment(data, "INV-9001", "1000.00")
                    time.sleep(0.01)
                    return updated, f"Recorded payment for {invoice.id}; balance is {invoice.balance_due}."

                try:
                    _, message = erp_state.update_data_with_audit(mutate, lambda item: item, db_path)
                    return message
                except ValueError as exc:
                    return str(exc)

            with ThreadPoolExecutor(max_workers=2) as executor:
                messages = sorted(executor.map(pay, range(2)))

            loaded = erp_state.load_data(db_path)
            audit = erp_state.load_audit(db_path)

        invoice = next(invoice for invoice in loaded.invoices if invoice.id == "INV-9001")
        self.assertEqual(
            [
                "Recorded payment for INV-9001; balance is 500.00.",
                "payment amount cannot exceed invoice balance",
            ],
            messages,
        )
        self.assertEqual("open", invoice.status)
        self.assertEqual("500.00", str(invoice.balance_due))
        self.assertEqual("13500.00", str(loaded.current_cash))
        self.assertEqual(["Recorded payment for INV-9001; balance is 500.00."], [entry["message"] for entry in audit])


if __name__ == "__main__":
    unittest.main()
