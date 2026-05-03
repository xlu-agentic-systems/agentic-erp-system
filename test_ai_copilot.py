from datetime import date
import unittest

import ai_copilot
import erp_core


class AICopilotTests(unittest.TestCase):
    def setUp(self) -> None:
        self.data = erp_core.seed_erp_data(date(2026, 5, 2))

    def test_build_insights_uses_core_rules(self) -> None:
        insights = ai_copilot.build_insights(self.data, erp_core)

        titles = [insight.title for insight in insights]
        self.assertIn("Low stock: Pump Assembly", titles)
        self.assertIn("Delayed purchase order: PO-1001", titles)
        self.assertIn("Overdue receivable: INV-9001", titles)

    def test_stock_question_recommends_only_low_stock_skus(self) -> None:
        answer = ai_copilot.answer_question("What stock is at risk?", self.data, erp_core)

        self.assertIn("PUMP-A", answer)
        self.assertIn("SENSOR-T", answer)
        self.assertNotIn("BOLT-10", answer)
        self.assertNotIn("VALVE-S", answer)

    def test_cash_question_returns_projection_details(self) -> None:
        answer = ai_copilot.answer_question("How does cashflow look?", self.data, erp_core)

        self.assertIn("Projected cash", answer)
        self.assertIn("Expected inflows", answer)
        self.assertIn("expected outflows", answer)

    def test_open_order_question_uses_customer_id_for_domain_records(self) -> None:
        answer = ai_copilot.answer_question("Show open orders", self.data, erp_core)

        self.assertIn("SO-5001 for C-10", answer)
        self.assertNotIn("for customer", answer)


if __name__ == "__main__":
    unittest.main()
