"""Tests for the PM tool executors and artifact sanitization."""
import pytest

from app.agents.tools.retrieve import execute_retrieve
from app.agents.tools.prd_generator import execute_prd_generator
from app.agents.tools.pre_mortem import execute_pre_mortem
from app.agents.tools.growth_audit import execute_growth_audit
from app.agents.tools.artifact_gen import execute_artifact_gen, sanitize_html_content
from app.agents.tools.ship30_essay import execute_ship30_essay


class TestRetrieveTool:
    def test_returns_chunks_with_metadata(self):
        result = execute_retrieve("product market fit survey", top_k=3)
        assert result["chunk_count"] > 0
        chunk = result["chunks"][0]
        for key in ("chunk_id", "guest", "episode_title", "excerpt", "relevance_score"):
            assert key in chunk
        assert 0.0 <= chunk["relevance_score"] <= 1.0

    def test_respects_top_k(self):
        result = execute_retrieve("retention", top_k=2)
        assert result["chunk_count"] <= 2

    def test_out_of_domain_query_still_returns_nearest(self):
        # Vector search always returns nearest neighbors; grounding refusal is
        # the LLM's job, not the retriever's.
        result = execute_retrieve("sourdough bread recipe", top_k=1)
        assert "chunks" in result


class TestPrdGenerator:
    def test_renders_markdown_with_sections(self):
        art = execute_prd_generator(
            title="Onboarding Revamp",
            problem_statement="Users drop before activation",
        )
        assert art["artifact_type"] == "prd"
        assert art["title"] == "PRD: Onboarding Revamp"
        for section in ("Problem Statement", "Goals", "User Stories", "Non-Goals"):
            assert section in art["content"]

    def test_includes_persona_and_metrics(self):
        art = execute_prd_generator(
            title="X", problem_statement="Y",
            target_persona="Growth Lead", goals_and_metrics="D30 retention",
        )
        assert "Growth Lead" in art["content"]
        assert "D30 retention" in art["content"]


class TestPreMortem:
    def test_uses_custom_failure_modes(self):
        art = execute_pre_mortem(
            initiative_name="Launch A",
            launch_context="Self-serve pivot",
            top_failure_modes="- Silent churn",
        )
        assert "Pre-Mortem Analysis: Launch A" in art["content"]
        assert "- Silent churn" in art["content"]

    def test_default_failure_modes_when_blank(self):
        art = execute_pre_mortem(initiative_name="B", launch_context="ctx")
        assert "Failure Mode 1" in art["content"]


class TestGrowthAudit:
    def test_renders_funnel_and_concern(self):
        art = execute_growth_audit(
            business_model="B2B SaaS",
            funnel_metrics="1000 visits -> 100 signups -> 10 paid",
            primary_concern="Activation drop",
        )
        assert "Growth & Metric Funnel Audit" in art["content"]
        assert "1000 visits" in art["content"]
        assert "Activation drop" in art["content"]


class TestArtifactGen:
    def test_html_gets_wrapped_in_document(self):
        art = execute_artifact_gen(
            title="Memo", artifact_type="html", content="<p>hi</p>"
        )
        assert art["content"].startswith("<!DOCTYPE html>")
        assert "Memo" in art["content"]

    def test_markdown_passthrough(self):
        art = execute_artifact_gen(
            title="Doc", artifact_type="markdown", content="# Title"
        )
        assert art["content"] == "# Title"

    def test_sanitize_strips_script_tags(self):
        dirty = "<p>ok</p><script>alert('x')</script>"
        assert "<script" not in sanitize_html_content(dirty).lower()

    def test_sanitize_neutralizes_js_urls_and_handlers(self):
        dirty = "<a href=\"javascript:evil()\">x</a><div onclick=\"boom()\">y</div>"
        clean = sanitize_html_content(dirty)
        assert "javascript:" not in clean
        assert "onclick" not in clean


class TestShip30Essay:
    def test_returns_brief_not_essay(self):
        res = execute_ship30_essay(topic="Loops", core_insights="insight")
        assert res["format_target"] == "ship30_atomic_essay"
        assert res["word_budget"] == "250-300 words"
        assert res["context"] == "insight"
