"""Tests for LLM provider internals: tool-call parsing, streaming, telemetry, fallback."""
import json

import httpx
import pytest

from app.llm.provider import (
    OllamaProvider,
    GroqProvider,
    GeminiProvider,
    MockProvider,
    LLMResponse,
    get_provider,
)
from app.llm.telemetry import telemetry, InstrumentedProvider, extract_token_usage


class TestMockProvider:
    @pytest.mark.asyncio
    async def test_dispatches_retrieve_tool_call(self):
        p = MockProvider()
        res = await p.generate(
            messages=[{"role": "user", "content": "What is the PMF survey?"}],
            system_prompt="s",
            tools=[{"name": "retrieve"}],
        )
        assert res.tool_calls and res.tool_calls[0].name == "retrieve"
        assert "PMF" in res.tool_calls[0].arguments["query"].upper() or res.tool_calls[0].arguments["query"]

    @pytest.mark.asyncio
    async def test_refuses_out_of_domain(self):
        p = MockProvider()
        res = await p.generate(
            messages=[{"role": "user", "content": "Give me a sourdough recipe"}],
            system_prompt="s",
        )
        assert "could not find" in res.content.lower()

    @pytest.mark.asyncio
    async def test_grounded_shreyas_answer(self):
        p = MockProvider()
        res = await p.generate(
            messages=[{"role": "user", "content": "Explain the LNO framework"}],
            system_prompt="s",
        )
        assert "Shreyas Doshi" in res.content
        assert "Leverage" in res.content


class TestOllamaParsing:
    def _provider(self):
        return OllamaProvider(base_url="http://localhost:99999", model="test")

    async def test_tool_call_name_inference_from_args(self, monkeypatch):
        p = self._provider()
        payload = {
            "message": {
                "content": "",
                "tool_calls": [
                    {"function": {"name": "", "arguments": json.dumps({"query": "pmf survey"})}}
                ],
            }
        }
        monkeypatch.setattr(httpx.AsyncClient, "post", _fake_post(payload))
        res = await p.generate(messages=[{"role": "user", "content": "q"}], system_prompt="s")
        assert res.tool_calls[0].name == "retrieve"


class _FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code
        self.text = json.dumps(payload)

    def json(self):
        return self._payload


def _fake_post(payload, status_code=200):
    async def _post(self, *args, **kwargs):
        return _FakeResponse(payload, status_code)
    return _post


class TestGroqParsing:
    @pytest.mark.asyncio
    async def test_parses_openai_style_tool_calls(self, monkeypatch):
        p = GroqProvider(api_key="k", model="m")
        payload = {
            "choices": [{
                "message": {
                    "content": None,
                    "tool_calls": [{
                        "id": "call_abc",
                        "function": {"name": "retrieve", "arguments": "{\"query\": \"loops\"}"},
                    }],
                }
            }],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5},
        }
        monkeypatch.setattr(httpx.AsyncClient, "post", _fake_post(payload))
        res = await p.generate(messages=[], system_prompt="s")
        assert res.tool_calls[0].name == "retrieve"
        assert res.tool_calls[0].arguments == {"query": "loops"}
        assert res.token_usage["prompt_tokens"] == 10


class TestGeminiParsing:
    @pytest.mark.asyncio
    async def test_parses_function_call_parts(self, monkeypatch):
        p = GeminiProvider(api_key="k", model="m")
        payload = {
            "candidates": [{
                "content": {"parts": [{"functionCall": {"name": "retrieve", "args": {"query": "pmf"}}}]},
                "finishReason": "STOP",
            }]
        }
        monkeypatch.setattr(httpx.AsyncClient, "post", _fake_post(payload))
        res = await p.generate(messages=[], system_prompt="s")
        assert res.tool_calls[0].name == "retrieve"
        assert res.tool_calls[0].arguments == {"query": "pmf"}

    def test_clean_schema_strips_unsupported_keys(self):
        schema = {
            "type": "object",
            "additionalProperties": False,
            "$schema": "http://x",
            "properties": {
                "q": {"type": "string", "default": "x", "minLength": 1}
            },
        }
        cleaned = GeminiProvider._clean_schema(schema)
        assert "additionalProperties" not in cleaned
        assert "$schema" not in cleaned
        assert "default" not in cleaned["properties"]["q"]
        assert cleaned["properties"]["q"]["type"] == "string"


class TestTelemetry:
    @pytest.mark.asyncio
    async def test_records_success_and_latency(self):
        class P(MockProvider):
            async def generate(self, *a, **k):
                res = await super().generate(*a, **k)
                return res

        wrapped = InstrumentedProvider(MockProvider())
        await wrapped.generate(
            messages=[{"role": "user", "content": "lno framework"}],
            system_prompt="s",
        )
        snap = telemetry.snapshot()
        assert snap["providers"]["mock"]["requests_total"] == 1
        assert snap["providers"]["mock"]["errors_total"] == 0
        assert snap["providers"]["mock"]["latency_ms_max"] >= 0

    @pytest.mark.asyncio
    async def test_records_errors(self):
        class Boom(MockProvider):
            async def generate(self, *a, **k):
                raise RuntimeError("exploded")

        wrapped = InstrumentedProvider(Boom())
        with pytest.raises(RuntimeError):
            await wrapped.generate(messages=[], system_prompt="s")
        snap = telemetry.snapshot()
        assert snap["providers"]["mock"]["errors_total"] == 1
        assert "exploded" in snap["providers"]["mock"]["last_error"]

    def test_extract_token_usage_shapes(self):
        assert extract_token_usage({"prompt_tokens": 3, "completion_tokens": 4}) == (3, 4)
        assert extract_token_usage({"prompt_eval_count": 7, "eval_count": 2}) == (7, 2)
        assert extract_token_usage(None) == (0, 0)
        assert extract_token_usage({"prompt_tokens": "x"}) == (0, 0)


class _ModelNotFound(RuntimeError):
    pass


class TestAutoFallback:
    @pytest.mark.asyncio
    async def test_falls_back_and_retries_on_model_not_found(self):
        class Flaky(OllamaProvider):
            def __init__(self):
                super().__init__(base_url="http://x", model="dead-model")
                self.attempts = 0

            async def generate(self, messages, system_prompt, tools=None, **kwargs):
                self.attempts += 1
                if self.attempts == 1:
                    raise RuntimeError(
                        "Groq API Error (404): model_not_found: The model `dead-model` does not exist"
                    )
                return LLMResponse(content="recovered", provider="x", model="live-model")

            async def discover_models(self):
                return ["live-model", "other-model"]

        wrapped = InstrumentedProvider(Flaky())
        res = await wrapped.generate(messages=[], system_prompt="s")
        assert res.content == "recovered"
        assert wrapped.model_name == "live-model"
        snap = telemetry.snapshot()
        assert snap["providers"]["ollama"]["fallbacks_total"] == 1
        assert snap["providers"]["ollama"]["requests_total"] == 1

    @pytest.mark.asyncio
    async def test_reraises_when_no_alternative_model(self):
        class Dead(OllamaProvider):
            def __init__(self):
                super().__init__(base_url="http://x", model="dead-model")

            async def generate(self, messages, system_prompt, tools=None, **kwargs):
                raise RuntimeError("model_not_found: gone forever")

            async def discover_models(self):
                return ["dead-model"]  # only the same dead model

        wrapped = InstrumentedProvider(Dead())
        with pytest.raises(RuntimeError, match="gone forever"):
            await wrapped.generate(messages=[], system_prompt="s")

    @pytest.mark.asyncio
    async def test_non_model_errors_do_not_trigger_fallback(self):
        class NetFail(OllamaProvider):
            def __init__(self):
                super().__init__(base_url="http://x", model="m")
                self.discover_called = False

            async def generate(self, messages, system_prompt, tools=None, **kwargs):
                raise ConnectionError("cannot connect")

            async def discover_models(self):
                self.discover_called = True
                return ["alt"]

        wrapped = InstrumentedProvider(NetFail())
        with pytest.raises(ConnectionError):
            await wrapped.generate(messages=[], system_prompt="s")
        assert wrapped._inner.discover_called is False
        snap = telemetry.snapshot()
        assert snap["providers"]["ollama"]["fallbacks_total"] == 0


class TestGetProviderFactory:
    def test_mock_roundtrip(self):
        assert isinstance(get_provider("mock"), InstrumentedProvider)

    def test_unknown_choice_defaults_to_ollama(self):
        p = get_provider("bogus-provider")
        assert p.provider_name == "ollama"

    def test_unconfigured_cloud_keys_fall_back_to_ollama(self, monkeypatch):
        from app.config import settings
        monkeypatch.setattr(settings, "GROQ_API_KEY", "")
        monkeypatch.setattr(settings, "GEMINI_API_KEY", "")
        assert get_provider("groq").provider_name == "ollama"
        assert get_provider("gemini").provider_name == "ollama"

    def test_instrument_false_returns_raw(self):
        assert not isinstance(get_provider("mock", instrument=False), InstrumentedProvider)
