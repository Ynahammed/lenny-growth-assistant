"""Tests for the Claude Agent SDK adapter (routing + fallback semantics)."""
from unittest.mock import patch

import pytest

from app.agents import sdk_adapter
from app.agents.sdk_adapter import AdapterError, _resolve_routing, sdk_available


def test_sdk_package_importable():
    """The claude-agent-sdk dependency is installed."""
    assert sdk_available() is True


def test_resolve_routing_ollama_uses_anthropic_compat_endpoint():
    with patch.object(sdk_adapter.settings, "OLLAMA_BASE_URL", "http://localhost:11434"), \
         patch.object(sdk_adapter.settings, "OLLAMA_MODEL", "llama3.2"):
        routing = _resolve_routing("ollama")
    # The Claude CLI appends /v1/messages itself, so the base URL must be the
    # bare origin — /v1 here would produce /v1/v1/messages and 404 upstream.
    assert routing["ANTHROPIC_BASE_URL"] == "http://localhost:11434"
    assert routing["ANTHROPIC_AUTH_TOKEN"]  # CLI needs a non-empty token
    assert routing["ANTHROPIC_MODEL"] == "llama3.2"


def test_resolve_routing_anthropic_requires_key():
    with patch.object(sdk_adapter.settings, "ANTHROPIC_API_KEY", ""):
        with pytest.raises(AdapterError, match="ANTHROPIC_API_KEY"):
            _resolve_routing("anthropic")


def test_resolve_routing_groq_unsupported():
    """Groq has no Anthropic-Messages endpoint; the SDK path must refuse it."""
    with pytest.raises(AdapterError, match="no Anthropic-Messages-compatible"):
        _resolve_routing("groq")


async def test_mock_provider_never_enters_sdk_path():
    """The mock provider raises AdapterError before any event is emitted."""
    from app.agents.sdk_adapter import execute_turn_stream_sdk
    with pytest.raises(AdapterError, match="mock"):
        async for _ in execute_turn_stream_sdk([], "hi", provider_type="mock"):
            pass


async def test_stream_turn_falls_back_to_native_on_adapter_error():
    """AdapterError from the SDK path is swallowed and the native loop runs."""
    from app.agents.agent_manager import AgentManager

    async def boom(*a, **k):
        raise AdapterError("simulated SDK failure")
        yield  # pragma: no cover

    agent = AgentManager(provider_type="mock")
    events = []
    with patch.object(sdk_adapter.settings, "AGENT_BACKEND", "claude-agent-sdk"), \
         patch("app.agents.sdk_adapter.execute_turn_stream_sdk", side_effect=boom):
        async for event in agent.execute_turn_stream([], "What is PMF?"):
            events.append(event)
    # Native loop ran: it emits status/error events from the mock provider.
    assert events, "native loop should have produced events after SDK failure"
    assert events[0]["type"] in {"status", "error"}


async def test_native_backend_setting_bypasses_sdk():
    """AGENT_BACKEND='native' never imports the adapter."""
    from app.agents.agent_manager import AgentManager

    agent = AgentManager(provider_type="mock")
    events = []
    with patch.object(sdk_adapter.settings, "AGENT_BACKEND", "native"):
        async for event in agent.execute_turn_stream([], "What is PMF?"):
            events.append(event)
    assert events
