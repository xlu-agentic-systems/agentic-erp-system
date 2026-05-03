"""Small OpenAI Responses API client for the ERP copilot.

The project intentionally avoids a runtime SDK dependency, so this module uses
the Python standard library. It loads local `.env` values when present and keeps
API keys out of logs and responses.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import ssl
import sys
from typing import Any, Callable
from urllib import error, request


OPENAI_RESPONSES_PATH = "/responses"
DEFAULT_BASE_URL = "https://api.openai.com/v1"
DEFAULT_MODEL = "gpt-5.4"
DEFAULT_TIMEOUT_SECONDS = 20.0


class LLMConfigurationError(RuntimeError):
    pass


class LLMResponseError(RuntimeError):
    pass


@dataclass(frozen=True)
class OpenAIConfig:
    api_key: str
    model: str = DEFAULT_MODEL
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS
    base_url: str = DEFAULT_BASE_URL
    ca_bundle: str | None = None


def load_dotenv(path: str | Path = ".env") -> None:
    """Load simple KEY=VALUE pairs into the environment if not already set."""

    env_path = Path(path)
    if not env_path.exists():
        return

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not key or key in os.environ:
            continue
        os.environ[key] = _strip_env_value(value.strip())


def _strip_env_value(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def config_from_env(path: str | Path = ".env") -> OpenAIConfig:
    load_dotenv(path)
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise LLMConfigurationError("OPENAI_API_KEY is not configured")

    timeout_raw = os.environ.get("OPENAI_TIMEOUT_SECONDS", str(DEFAULT_TIMEOUT_SECONDS)).strip()
    try:
        timeout_seconds = float(timeout_raw)
    except ValueError as exc:
        raise LLMConfigurationError("OPENAI_TIMEOUT_SECONDS must be numeric") from exc
    if timeout_seconds <= 0:
        raise LLMConfigurationError("OPENAI_TIMEOUT_SECONDS must be positive")

    return OpenAIConfig(
        api_key=api_key,
        model=os.environ.get("OPENAI_MODEL", DEFAULT_MODEL).strip() or DEFAULT_MODEL,
        timeout_seconds=timeout_seconds,
        base_url=os.environ.get("OPENAI_BASE_URL", DEFAULT_BASE_URL).strip() or DEFAULT_BASE_URL,
        ca_bundle=_ca_bundle_from_env(),
    )


def is_configured(path: str | Path = ".env") -> bool:
    try:
        config_from_env(path)
    except LLMConfigurationError:
        return False
    return True


class OpenAIResponsesClient:
    def __init__(
        self,
        config: OpenAIConfig | None = None,
        opener: Callable[..., Any] | None = None,
    ) -> None:
        self.config = config or config_from_env()
        self.opener = opener or request.urlopen
        self.ssl_context = _build_ssl_context(self.config.ca_bundle)

    def create_text_response(
        self,
        *,
        instructions: str,
        input_text: str,
        max_output_tokens: int = 500,
    ) -> str:
        payload = {
            "model": self.config.model,
            "instructions": instructions,
            "input": input_text,
            "max_output_tokens": max_output_tokens,
            "store": False,
        }
        response_json = self._post_json(payload)
        text = extract_output_text(response_json)
        if not text:
            raise LLMResponseError("OpenAI response did not contain output text")
        return text.strip()

    def _post_json(self, payload: dict[str, Any]) -> dict[str, Any]:
        url = self.config.base_url.rstrip("/") + OPENAI_RESPONSES_PATH
        body = json.dumps(payload).encode("utf-8")
        req = request.Request(
            url,
            data=body,
            method="POST",
            headers={
                "Authorization": f"Bearer {self.config.api_key}",
                "Content-Type": "application/json",
                "User-Agent": "agentic-erp-system/0.1",
            },
        )
        try:
            if self.opener is request.urlopen and self.ssl_context is not None:
                response = self.opener(req, timeout=self.config.timeout_seconds, context=self.ssl_context)
            else:
                response = self.opener(req, timeout=self.config.timeout_seconds)
            with response as resp:
                raw = resp.read()
        except error.HTTPError as exc:
            detail = _read_error_detail(exc)
            raise LLMResponseError(f"OpenAI API returned HTTP {exc.code}: {detail}") from exc
        except error.URLError as exc:
            raise LLMResponseError(f"OpenAI API request failed: {exc.reason}") from exc

        try:
            parsed = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise LLMResponseError("OpenAI API returned invalid JSON") from exc
        if not isinstance(parsed, dict):
            raise LLMResponseError("OpenAI API returned an unexpected payload")
        if parsed.get("error"):
            raise LLMResponseError(f"OpenAI API error: {parsed['error']}")
        return parsed


def _read_error_detail(exc: error.HTTPError) -> str:
    try:
        raw = exc.read().decode("utf-8", errors="replace")
    except Exception:
        return "no error body"
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return raw[:500]
    message = parsed.get("error", {}).get("message") if isinstance(parsed, dict) else None
    return str(message or parsed)[:500]


def _ca_bundle_from_env() -> str | None:
    explicit = os.environ.get("OPENAI_CA_BUNDLE") or os.environ.get("SSL_CERT_FILE")
    if explicit:
        return explicit
    try:
        import certifi  # type: ignore[import-not-found]
    except ImportError:
        return None
    return certifi.where()


def _build_ssl_context(ca_bundle: str | None) -> ssl.SSLContext | None:
    if not ca_bundle:
        return None
    try:
        return ssl.create_default_context(cafile=ca_bundle)
    except OSError as exc:
        raise LLMConfigurationError(f"Cannot load CA bundle: {ca_bundle}") from exc


def extract_output_text(response_json: dict[str, Any]) -> str:
    if isinstance(response_json.get("output_text"), str):
        return response_json["output_text"]

    chunks: list[str] = []
    for item in response_json.get("output", []) or []:
        if not isinstance(item, dict):
            continue
        for content in item.get("content", []) or []:
            if not isinstance(content, dict):
                continue
            if content.get("type") == "output_text" and isinstance(content.get("text"), str):
                chunks.append(content["text"])
    return "\n".join(chunks).strip()


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    prompt = " ".join(args).strip() or "Reply with OK if the live OpenAI Responses API call worked."
    client = OpenAIResponsesClient()
    answer = client.create_text_response(
        instructions="You are a terse smoke-test assistant. Do not mention secrets.",
        input_text=prompt,
        max_output_tokens=80,
    )
    print(answer)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
