import unittest

import app


class AppHelperTests(unittest.TestCase):
    def test_parse_content_length_rejects_bad_values(self) -> None:
        self.assertEqual(0, app.parse_content_length(None))
        self.assertEqual(12, app.parse_content_length("12"))

        with self.assertRaises(ValueError):
            app.parse_content_length("bad")

        with self.assertRaises(ValueError):
            app.parse_content_length("-1")

    def test_ask_erp_prefers_core_seed_for_stock_answers(self) -> None:
        answer = app.ask_erp("What stock is at risk?", app.load_dashboard_data())

        self.assertIn("PUMP-A", answer)
        self.assertIn("SENSOR-T", answer)
        self.assertNotIn("BOLT-10", answer)
        self.assertNotIn("VALVE-S", answer)


if __name__ == "__main__":
    unittest.main()
