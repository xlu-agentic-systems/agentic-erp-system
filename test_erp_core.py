from datetime import date, timedelta
from decimal import Decimal
import unittest

from erp_core import (
    ERPData,
    InventoryItem,
    Invoice,
    OrderLine,
    Product,
    PurchaseOrder,
    SalesOrder,
    Vendor,
    cash_projection,
    delayed_purchase_orders,
    fulfillment_risks,
    inventory_value,
    low_stock_items,
    money,
    open_sales_orders,
    overdue_invoices,
    seed_erp_data,
)


class SeededERPDataTests(unittest.TestCase):
    def setUp(self) -> None:
        self.today = date(2026, 5, 2)
        self.data = seed_erp_data(self.today)

    def test_seeded_entities_cover_core_erp_records(self) -> None:
        self.assertEqual(4, len(self.data.products))
        self.assertEqual(2, len(self.data.vendors))
        self.assertEqual(2, len(self.data.customers))
        self.assertEqual(4, len(self.data.inventory))
        self.assertEqual(3, len(self.data.purchase_orders))
        self.assertEqual(3, len(self.data.sales_orders))
        self.assertEqual(3, len(self.data.invoices))

    def test_low_stock_items_use_available_quantity(self) -> None:
        low_stock_skus = [product.sku for product, _ in low_stock_items(self.data)]

        self.assertEqual(["PUMP-A", "SENSOR-T"], low_stock_skus)

    def test_delayed_purchase_orders_ignore_received_orders(self) -> None:
        delayed = delayed_purchase_orders(self.data, self.today)

        self.assertEqual(["PO-1001"], [po.id for po in delayed])

    def test_overdue_invoices_return_only_unpaid_balances(self) -> None:
        overdue = overdue_invoices(self.data, self.today)

        self.assertEqual(["INV-9001"], [invoice.id for invoice in overdue])
        self.assertEqual(Decimal("1500.00"), overdue[0].balance_due)

    def test_inventory_value_uses_unit_cost_and_on_hand_quantity(self) -> None:
        self.assertEqual(Decimal("2090.60"), inventory_value(self.data))

    def test_open_sales_orders_exclude_shipped_orders(self) -> None:
        self.assertEqual(["SO-5001", "SO-5002"], [so.id for so in open_sales_orders(self.data)])

    def test_cash_projection_includes_windowed_receipts_and_payments(self) -> None:
        self.assertEqual(Decimal("13055.50"), cash_projection(self.data, self.today, days=30))

    def test_cash_projection_rejects_negative_windows(self) -> None:
        with self.assertRaises(ValueError):
            cash_projection(self.data, self.today, days=-1)

    def test_fulfillment_risks_show_orders_that_pressure_reorder_bands(self) -> None:
        risks = fulfillment_risks(self.data)

        pump_risk = next(risk for risk in risks if risk["sku"] == "PUMP-A")
        self.assertEqual("SO-5001", pump_risk["order_id"])
        self.assertEqual("Apex Manufacturing", pump_risk["customer"])
        self.assertEqual("At risk", pump_risk["status"])
        self.assertEqual(3, pump_risk["required"])
        self.assertEqual(8, pump_risk["available"])
        self.assertIn("PO-1001", pump_risk["next_receipt"])


class CustomERPDataTests(unittest.TestCase):
    def test_status_comparisons_are_case_insensitive(self) -> None:
        today = date(2026, 5, 2)
        product = Product("P-1", "WIDGET", "Widget", money("4.00"), money("9.00"), 5)
        data = ERPData(
            products=(product,),
            vendors=(Vendor("V-1", "Acme Supply", 30),),
            customers=(),
            inventory=(InventoryItem("P-1", 5, 0),),
            purchase_orders=(
                PurchaseOrder(
                    "PO-1",
                    "V-1",
                    today - timedelta(days=10),
                    today - timedelta(days=1),
                    "Open",
                    (OrderLine("P-1", 2, money("4.00")),),
                ),
            ),
            sales_orders=(
                SalesOrder("SO-1", "C-1", today, today, "Shipped", (OrderLine("P-1", 1, money("9.00")),)),
                SalesOrder("SO-2", "C-1", today, today, "OPEN", (OrderLine("P-1", 1, money("9.00")),)),
            ),
            invoices=(
                Invoice("INV-1", "C-1", today - timedelta(days=20), today - timedelta(days=1), "OPEN", money("10.00")),
                Invoice("INV-2", "C-1", today - timedelta(days=20), today - timedelta(days=1), "PAID", money("10.00"), money("10.00")),
            ),
            current_cash=money("100.00"),
        )

        self.assertEqual(["PO-1"], [po.id for po in delayed_purchase_orders(data, today)])
        self.assertEqual(["INV-1"], [invoice.id for invoice in overdue_invoices(data, today)])
        self.assertEqual(["SO-2"], [order.id for order in open_sales_orders(data)])

    def test_service_functions_accept_custom_records(self) -> None:
        today = date(2026, 5, 2)
        product = Product("P-1", "WIDGET", "Widget", money("4.00"), money("9.00"), 5)
        data = ERPData(
            products=(product,),
            vendors=(Vendor("V-1", "Acme Supply", 30),),
            customers=(),
            inventory=(InventoryItem("P-1", 5, 1),),
            purchase_orders=(
                PurchaseOrder(
                    "PO-1",
                    "V-1",
                    today - timedelta(days=4),
                    today + timedelta(days=3),
                    "partially_received",
                    (OrderLine("P-1", 10, money("4.25")),),
                ),
            ),
            sales_orders=(
                SalesOrder(
                    "SO-1",
                    "C-1",
                    today,
                    today + timedelta(days=1),
                    "closed",
                    (OrderLine("P-1", 1, money("9.00")),),
                ),
            ),
            invoices=(
                Invoice(
                    "INV-1",
                    "C-1",
                    today - timedelta(days=10),
                    today + timedelta(days=5),
                    "open",
                    money("20.00"),
                    money("2.00"),
                ),
            ),
            current_cash=money("100.00"),
        )

        self.assertEqual(["Widget"], [product.name for product, _ in low_stock_items(data)])
        self.assertEqual(Decimal("20.00"), inventory_value(data))
        self.assertEqual([], open_sales_orders(data))
        self.assertEqual(Decimal("75.50"), cash_projection(data, today, days=7))


if __name__ == "__main__":
    unittest.main()
