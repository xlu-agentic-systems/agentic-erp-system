from datetime import date
from decimal import Decimal
import unittest

import adaptive_erp
import erp_core


class AdaptiveERPWorkflowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.today = date(2026, 5, 2)
        self.data = erp_core.seed_erp_data(self.today)

    def test_language_variants_create_purchase_orders(self) -> None:
        variants = (
            "reorder pump assembly",
            "please buy 40 PUMP-A from the best supplier",
            "create a purchase order for Sensor T",
            "restock SENSOR-T",
        )

        for phrase in variants:
            with self.subTest(phrase=phrase):
                updated, result = adaptive_erp.execute_goal(phrase, self.data, self.today)

                self.assertTrue(result.success)
                self.assertTrue(result.changed)
                self.assertEqual("create_purchase_order", result.action)
                self.assertEqual(len(self.data.purchase_orders) + 1, len(updated.purchase_orders))
                self.assertIn(updated.purchase_orders[-1].status, {"open", "Open"})

    def test_language_variants_receive_purchase_orders(self) -> None:
        for phrase in ("receive PO-1001", "PO 1001 arrived", "mark purchase order po-1001 received"):
            with self.subTest(phrase=phrase):
                updated, result = adaptive_erp.execute_goal(phrase, self.data, self.today)
                pump_inventory = next(item for item in updated.inventory if item.product_id == "P-200")
                received = next(po for po in updated.purchase_orders if po.id == "PO-1001")

                self.assertTrue(result.success)
                self.assertTrue(result.changed)
                self.assertEqual("receive_purchase_order", result.action)
                self.assertEqual("received", received.status)
                self.assertEqual(26, pump_inventory.quantity_on_hand)

    def test_language_variants_record_customer_payment(self) -> None:
        for phrase in ("mark INV-9001 paid", "record payment for invoice inv 9001", "collect overdue invoice INV-9001"):
            with self.subTest(phrase=phrase):
                updated, result = adaptive_erp.execute_goal(phrase, self.data, self.today)
                invoice = next(invoice for invoice in updated.invoices if invoice.id == "INV-9001")

                self.assertTrue(result.success)
                self.assertTrue(result.changed)
                self.assertEqual("record_invoice_payment", result.action)
                self.assertEqual("paid", invoice.status)
                self.assertEqual(Decimal("0.00"), invoice.balance_due)
                self.assertEqual(Decimal("14000.00"), updated.current_cash)

    def test_unknown_goal_is_actionable_without_changing_data(self) -> None:
        updated, result = adaptive_erp.execute_goal("make the business better", self.data, self.today)

        self.assertFalse(result.success)
        self.assertFalse(result.changed)
        self.assertIs(updated, self.data)
        self.assertIn("Try", result.message)


if __name__ == "__main__":
    unittest.main()
