"""Tests for AgentManager orchestration logic (using the mock provider)."""
import pytest

from app.agents.agent_manager import AgentManager, generate_suggested_follow_ups
from app.llm.provider import LLMResponse, ToolCall
from app.rag.query_rewrite import is_vague_query, build_fallback_query, rewrite_query_for_search


class _RewriteStubProvider:
    """Minimal provider stub returning a canned generate() response."""

    def __init__(self, content):
        self.content = content
        self.calls = []

    async def generate(self, messages, system_prompt, tools=None, **kwargs):
        self.calls.append({"messages": messages, "system_prompt": system_prompt})
        if isinstance(self.content, Exception):
            raise self.content
        return LLMResponse(content=self.content, provider="stub", model="stub")


class TestQueryRewrite:
    def test_vague_detection(self):
        for q in ["what about retention?", "why?", "tell me more", "and how does that work", "it"]:
            assert is_vague_query(q), q

    def test_self_contained_detection(self):
        for q in [
            "How did Rahul Vohra measure product-market fit at Superhuman?",
            "How do I improve user retention in a B2B SaaS product after PMF?",
            "What is the LNO framework for task prioritization?",
        ]:
            assert not is_vague_query(q), q

    def test_fallback_stitches_last_user_message(self):
        history = [
            {"role": "user", "content": "How did Rahul Vohra measure PMF?"},
            {"role": "assistant", "content": "He used the Sean Ellis survey."},
        ]
        out = build_fallback_query("what about retention?", history)
        assert out == "How did Rahul Vohra measure PMF? — what about retention?"

    @pytest.mark.asyncio
    async def test_self_contained_query_skips_llm(self):
        provider = _RewriteStubProvider("should not be called")
        result = await rewrite_query_for_search(
            "What is the LNO framework?",
            [{"role": "user", "content": "earlier question"}],
            provider=provider,
        )
        assert result["method"] == "self_contained"
        assert result["rewritten"] is False
        assert provider.calls == []

    @pytest.mark.asyncio
    async def test_vague_query_rewritten_by_llm(self):
        provider = _RewriteStubProvider(
            "How do I improve user retention for a B2B SaaS product after PMF?"
        )
        history = [
            {"role": "user", "content": "How did Rahul Vohra measure PMF?"},
            {"role": "assistant", "content": "He used the Sean Ellis survey."},
        ]
        result = await rewrite_query_for_search("what about retention?", history, provider=provider)
        assert result["method"] == "llm"
        assert "retention" in result["query"].lower()
        assert "B2B SaaS" in result["query"]
        assert provider.calls[0]["system_prompt"].startswith("You rewrite")

    @pytest.mark.asyncio
    async def test_provider_failure_uses_deterministic_fallback(self):
        provider = _RewriteStubProvider(RuntimeError("provider down"))
        history = [{"role": "user", "content": "How did Rahul Vohra measure PMF?"}]
        result = await rewrite_query_for_search("what about retention?", history, provider=provider)
        assert result["method"] == "fallback"
        assert "PMF" in result["query"] and "retention" in result["query"].lower()

    @pytest.mark.asyncio
    async def test_junk_llm_output_uses_fallback(self):
        provider = _RewriteStubProvider("Here is your rewritten query: ...")
        history = [{"role": "user", "content": "How did Rahul Vohra measure PMF?"}]
        result = await rewrite_query_for_search("what about retention?", history, provider=provider)
        assert result["method"] == "fallback"

    @pytest.mark.asyncio
    async def test_agent_retrieve_uses_rewritten_query_end_to_end(self):
        # MockProvider answers with a retrieve tool call for the vague phrase;
        # the agent must embed the CONTEXTUALIZED query, not the fragment.
        agent = AgentManager(provider_type="mock")
        result = await agent.execute_turn(
            [
                {"role": "user", "content": "How did Rahul Vohra measure PMF?"},
                {"role": "assistant", "content": "He used the Sean Ellis survey with a 40% threshold."},
            ],
            "what about retention?",
        )
        assert result["sources"], "contextualized follow-up should retrieve sources"


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
        out = await agent._execute_tool(
            FakeTC(), "How did Rahul Vohra measure product market fit?", collected, artifacts
        )
        assert collected, "sources should be collected from user-message fallback"


class TestRefusalGate:
    """Off-topic questions must surface a no-evidence signal to the LLM, not
    forced nearest-neighbor chunks."""

    @pytest.mark.asyncio
    async def test_off_topic_tool_output_carries_refusal_directive(self):
        agent = AgentManager(provider_type="mock")

        class FakeTC:
            name = "retrieve"
            id = "c2"
            arguments = {"query": "sourdough bread recipe"}

        collected, artifacts = [], []
        out = await agent._execute_tool(FakeTC(), "how do I bake sourdough", collected, artifacts)
        assert collected == [], "no sources should be collected for off-topic queries"
        assert "NO_RELEVANT_EVIDENCE" in out
        assert "MUST refuse" in out

    @pytest.mark.asyncio
    async def test_on_topic_tool_output_includes_chunks(self):
        agent = AgentManager(provider_type="mock")

        class FakeTC:
            name = "retrieve"
            id = "c3"
            arguments = {"query": "product market fit survey"}

        collected, artifacts = [], []
        out = await agent._execute_tool(FakeTC(), "How is PMF measured?", collected, artifacts)
        assert collected, "on-topic queries should still collect sources"
        assert "NO_RELEVANT_EVIDENCE" not in out
        assert "GUEST" in out

    @pytest.mark.asyncio
    async def test_turn_filters_pin_guest_across_tool_calls(self):
        # UI-supplied filters apply even when the LLM omits them from its
        # retrieve arguments.
        agent = AgentManager(provider_type="mock")
        agent._turn_filters = {"guest": "April Dunford"}

        class FakeTC:
            name = "retrieve"
            id = "c4"
            arguments = {"query": "positioning against competitors"}

        collected, artifacts = [], []
        await agent._execute_tool(FakeTC(), "positioning", collected, artifacts)
        assert collected, "filtered retrieval should collect sources"
        assert all(s["guest"] == "April Dunford" for s in collected)

    @pytest.mark.asyncio
    async def test_turn_filters_override_llm_chosen_guest(self):
        # User intent wins: if the UI pins a guest, the LLM naming a different
        # guest in its tool arguments must not unpin it.
        agent = AgentManager(provider_type="mock")
        agent._turn_filters = {"guest": "Rahul Vohra"}

        class FakeTC:
            name = "retrieve"
            id = "c6"
            arguments = {"query": "PMF measurement", "guest": "Shreyas Doshi"}

        collected, artifacts = [], []
        await agent._execute_tool(FakeTC(), "PMF measurement", collected, artifacts)
        assert collected
        assert all(s["guest"] == "Rahul Vohra" for s in collected)

    @pytest.mark.asyncio
    async def test_unknown_guest_tool_output_carries_filter_error(self):
        agent = AgentManager(provider_type="mock")

        class FakeTC:
            name = "retrieve"
            id = "c5"
            arguments = {"query": "positioning", "guest": "Not A Guest"}

        collected, artifacts = [], []
        out = await agent._execute_tool(FakeTC(), "positioning", collected, artifacts)
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
