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
        # On-topic fallback text: the numeric arg falls back to the user's
        # message, which must still clear the relevance cutoff to collect sources.
        out = agent._execute_tool(
            FakeTC(), "How did Rahul Vohra measure product market fit?", collected, artifacts
        )
        assert collected, "sources should be collected from user-message fallback"


class TestRefusalGate:
    """Off-topic questions must surface a no-evidence signal to the LLM, not
    forced nearest-neighbor chunks."""

    def test_off_topic_tool_output_carries_refusal_directive(self):
        agent = AgentManager(provider_type="mock")

        class FakeTC:
            name = "retrieve"
            id = "c2"
            arguments = {"query": "sourdough bread recipe"}

        collected, artifacts = [], []
        out = agent._execute_tool(FakeTC(), "how do I bake sourdough", collected, artifacts)
        assert collected == [], "no sources should be collected for off-topic queries"
        assert "NO_RELEVANT_EVIDENCE" in out
        assert "MUST refuse" in out

    def test_on_topic_tool_output_includes_chunks(self):
        agent = AgentManager(provider_type="mock")

        class FakeTC:
            name = "retrieve"
            id = "c3"
            arguments = {"query": "product market fit survey"}

        collected, artifacts = [], []
        out = agent._execute_tool(FakeTC(), "How is PMF measured?", collected, artifacts)
        assert collected, "on-topic queries should still collect sources"
        assert "NO_RELEVANT_EVIDENCE" not in out
        assert "GUEST" in out

    def test_turn_filters_pin_guest_across_tool_calls(self):
        # UI-supplied filters apply even when the LLM omits them from its
        # retrieve arguments.
        agent = AgentManager(provider_type="mock")
        agent._turn_filters = {"guest": "April Dunford"}

        class FakeTC:
            name = "retrieve"
            id = "c4"
            arguments = {"query": "positioning against competitors"}

        collected, artifacts = [], []
        agent._execute_tool(FakeTC(), "positioning", collected, artifacts)
        assert collected, "filtered retrieval should collect sources"
        assert all(s["guest"] == "April Dunford" for s in collected)

    def test_turn_filters_override_llm_chosen_guest(self):
        # User intent wins: if the UI pins a guest, the LLM naming a different
        # guest in its tool arguments must not unpin it.
        agent = AgentManager(provider_type="mock")
        agent._turn_filters = {"guest": "Rahul Vohra"}

        class FakeTC:
            name = "retrieve"
            id = "c6"
            arguments = {"query": "PMF measurement", "guest": "Shreyas Doshi"}

        collected, artifacts = [], []
        agent._execute_tool(FakeTC(), "PMF measurement", collected, artifacts)
        assert collected
        assert all(s["guest"] == "Rahul Vohra" for s in collected)

    def test_unknown_guest_tool_output_carries_filter_error(self):
        agent = AgentManager(provider_type="mock")

        class FakeTC:
            name = "retrieve"
            id = "c5"
            arguments = {"query": "positioning", "guest": "Not A Guest"}

        collected, artifacts = [], []
        out = agent._execute_tool(FakeTC(), "positioning", collected, artifacts)
        assert collected == []
        assert "FILTER_ERROR" in out
        assert "Available guests" in out


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
