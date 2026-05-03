from datetime import date
import unittest

import ai_copilot
import erp_core


class FakeLLMClient:
    def __init__(self) -> None:
        self.instructions = ""
        self.input_text = ""

    def create_text_response(self, *, instructions: str, input_text: str, max_output_tokens: int = 500) -> str:
        self.instructions = instructions
        self.input_text = input_text
        return "LLM-backed ERP answer"


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

    def test_llm_answer_uses_openai_client_with_rules_context(self) -> None:
        client = FakeLLMClient()

        answer = ai_copilot.answer_question_with_llm("What needs attention?", self.data, erp_core, client)

        self.assertEqual("LLM-backed ERP answer", answer)
        self.assertIn("read-only ERP copilot", client.instructions)
        self.assertIn("deterministic_rules_answer", client.input_text)
        self.assertIn("Low stock", client.input_text)


if __name__ == "__main__":
    unittest.main()
