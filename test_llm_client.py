import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import llm_client


class FakeHTTPResponse:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload

    def __enter__(self) -> "FakeHTTPResponse":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")


class LLMClientTests(unittest.TestCase):
    def test_dotenv_loader_does_not_override_existing_environment(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            env_path = Path(tmp) / ".env"
            ca_path = Path(tmp) / "ca.pem"
            ca_path.write_text("", encoding="utf-8")
            env_path.write_text(
                f"OPENAI_API_KEY=file-key\nOPENAI_MODEL='gpt-test'\nOPENAI_TIMEOUT_SECONDS=7\nOPENAI_CA_BUNDLE={ca_path}\n",
                encoding="utf-8",
            )
            with patch.dict(os.environ, {"OPENAI_API_KEY": "existing-key"}, clear=True):
                config = llm_client.config_from_env(env_path)

        self.assertEqual("existing-key", config.api_key)
        self.assertEqual("gpt-test", config.model)
        self.assertEqual(7.0, config.timeout_seconds)
        self.assertEqual(str(ca_path), config.ca_bundle)

    def test_extract_output_text_reads_responses_output_items(self) -> None:
        response = {
            "output": [
                {
                    "type": "message",
                    "content": [
                        {"type": "output_text", "text": "First sentence."},
                        {"type": "output_text", "text": "Second sentence."},
                    ],
                }
            ]
        }

        self.assertEqual("First sentence.\nSecond sentence.", llm_client.extract_output_text(response))

    def test_create_text_response_posts_to_responses_api(self) -> None:
        captured = {}

        def fake_opener(req, timeout):
            captured["url"] = req.full_url
            captured["timeout"] = timeout
            captured["headers"] = dict(req.header_items())
            captured["payload"] = json.loads(req.data.decode("utf-8"))
            return FakeHTTPResponse({"output": [{"content": [{"type": "output_text", "text": "LLM answer"}]}]})

        config = llm_client.OpenAIConfig(api_key="test-key", model="gpt-test", timeout_seconds=3)
        client = llm_client.OpenAIResponsesClient(config=config, opener=fake_opener)

        answer = client.create_text_response(instructions="Be brief.", input_text="Hello")

        self.assertEqual("LLM answer", answer)
        self.assertEqual("https://api.openai.com/v1/responses", captured["url"])
        self.assertEqual(3, captured["timeout"])
        self.assertEqual("gpt-test", captured["payload"]["model"])
        self.assertEqual("Be brief.", captured["payload"]["instructions"])
        self.assertEqual("Hello", captured["payload"]["input"])
        self.assertFalse(captured["payload"]["store"])
        self.assertIn("Authorization", captured["headers"])


if __name__ == "__main__":
    unittest.main()
