"""Tests for AgentManager orchestration logic (using the mock provider)."""
import pytest

from app.agents.agent_manager import AgentManager, generate_suggested_follow_ups
from app.llm.provider import LLMResponse, ToolCall


class TestAgentTurn:
    @pytest.mark.asyncio
    async def test_grounded_turn_includes_sources_and_content(self):
        agent = AgentManager(provider_type="mock")
        result = await agent.execute_turn([], "What is the LNO framework?")
        assert result["role"] == "assistant"
        assert "Shreyas" in result["content"] or result["sources"]
        assert result["provider"] == "mock"
        assert isinstance(result["follow_ups"], list) and result["follow_ups"]

    @pytest.mark.asyncio
    async def test_artifact_tools_generate_artifacts(self):
        agent = AgentManager(provider_type="mock")
        result = await agent.execute_turn([], "Run a pre-mortem on our launch")
        assert any(a["artifact_type"] == "pre_mortem" for a in result["artifacts"])

    @pytest.mark.asyncio
    async def test_streaming_yields_expected_event_sequence(self):
        agent = AgentManager(provider_type="mock")
        events = []
        async for event in agent.execute_turn_stream([], "pmf survey 40% benchmark"):
            events.append(event)
        types = [e["type"] for e in events]
        assert types[0] == "status"
        assert "sources" in types or "token" in types
        assert types[-1] == "done"
        done = events[-1]
        assert "full_content" in done and "follow_ups" in done


class TestFollowUpGeneration:
    def test_lno_topic(self):
        followups = generate_suggested_follow_ups("lno framework", "shreyas")
        assert any("LNO" in f for f in followups)

    def test_default_fallback_pills(self):
        followups = generate_suggested_follow_ups("hello", "hi")
        assert len(follow_ups := followups) == 3
        assert all(isinstance(f, str) for f in follow_ups)

    def test_pmf_topic(self):
        followups = generate_suggested_follow_ups("rahul vohra", "superhuman engine")
        assert any("Rahul Vohra" in f for f in followups)


class TestToolArgumentHandling:
    @pytest.mark.asyncio
    async def test_retrieve_with_numeric_query_falls_back_to_user_message(self):
        agent = AgentManager(provider_type="mock")
        sources = []

        class FakeTC:
            name = "retrieve"
            id = "c1"
            arguments = {"query": 12345}

        collected, artifacts = [], []
        out = agent._execute_tool(FakeTC(), "real user question", collected, artifacts)
        assert collected, "sources should be collected from user-message fallback"


class TestProviderErrorSurface:
    @pytest.mark.asyncio
    async def test_provider_exception_becomes_friendly_message(self, monkeypatch):
        agent = AgentManager(provider_type="mock")

        async def boom(*a, **k):
            raise RuntimeError("connection refused")

        monkeypatch.setattr(agent, "provider", type("P", (), {
            "provider_name": "mock",
            "model_name": "m",
            "generate": staticmethod(boom),
        })())
        result = await agent.execute_turn([], "hi")
        assert "Communication error" in result["content"]
        assert result["sources"] == []
