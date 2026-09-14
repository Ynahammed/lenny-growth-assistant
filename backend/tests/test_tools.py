"""Tests for the PM tool executors and artifact sanitization."""
import pytest

from app.agents.tools.retrieve import execute_retrieve
from app.agents.tools.prd_generator import execute_prd_generator
from app.agents.tools.pre_mortem import execute_pre_mortem
from app.agents.tools.growth_audit import execute_growth_audit
from app.agents.tools.artifact_gen import execute_artifact_gen, sanitize_html_content
from app.agents.tools.ship30_essay import execute_ship30_essay


class TestRetrieveTool:
    def test_returns_chunks_with_both_scores(self):
        result = execute_retrieve("product market fit survey", top_k=3)
        assert result["chunk_count"] > 0
        chunk = result["chunks"][0]
        for key in ("chunk_id", "guest", "episode_title", "excerpt", "relevance_score", "retrieval_score"):
            assert key in chunk
        assert 0.0 <= chunk["retrieval_score"] <= 1.0
        assert 0.0 <= chunk["relevance_score"] <= 1.0

    def test_respects_top_k(self):
        result = execute_retrieve("growth loops", top_k=2)
        assert result["chunk_count"] <= 2

    def test_out_of_domain_query_refused(self):
        # The cosine gate drops far-below-threshold candidates; grounding
        # refusal is enforced at retrieval time, not left to LLM vibes.
        result = execute_retrieve("sourdough bread recipe", top_k=1)
        assert result["chunk_count"] == 0
        assert result.get("no_relevant_evidence") is True


class TestRelevanceCutoff:
    """Gate on bge cosine (topical admission), rerank for ordering."""

    def test_off_topic_query_refused(self):
        # bge cosine: off-topic queries stay under ~0.58; the default gate is 0.62.
        result = execute_retrieve("sourdough bread recipe", top_k=4)
        assert result["chunk_count"] == 0
        assert result["chunks"] == []
        assert result["no_relevant_evidence"] is True

    def test_on_topic_query_passes_gate(self):
        result = execute_retrieve("growth loops vs funnels activation", top_k=4)
        assert result["chunk_count"] >= 3
        assert "no_relevant_evidence" not in result
        assert all(c["retrieval_score"] >= 0.62 for c in result["chunks"])

    def test_borderline_growth_query_not_refused(self):
        # churn/retention phrasing scores ~0.69 on bge cosine — must clear the
        # gate even though the cross-encoder scores its excerpts low.
        result = execute_retrieve("how do I reduce churn in my SaaS funnel", top_k=4)
        assert result["chunk_count"] >= 3

    def test_cutoff_zero_restores_legacy_nearest_neighbor(self):
        result = execute_retrieve("sourdough bread recipe", top_k=2, relevance_cutoff=0.0)
        assert result["chunk_count"] == 2
        assert "no_relevant_evidence" not in result

    def test_reranker_orders_answer_bearing_chunks_first(self):
        result = execute_retrieve("How did Rahul Vohra measure product-market fit?", top_k=4)
        scores = [c["relevance_score"] for c in result["chunks"]]
        assert scores == sorted(scores, reverse=True)

    def test_rerank_disabled_falls_back_to_cosine_ordering(self, monkeypatch):
        from app.agents.tools import retrieve as retrieve_mod
        monkeypatch.setattr(retrieve_mod.settings, "RERANK_ENABLED", False)
        result = retrieve_mod.execute_retrieve("growth loops vs funnels activation", top_k=4)
        assert result["chunk_count"] >= 3
        # Without the reranker, relevance_score is the cosine retrieval score.
        scores = [c["relevance_score"] for c in result["chunks"]]
        assert scores == sorted(scores, reverse=True)

    def test_extreme_cutoff_drops_everything(self):
        result = execute_retrieve("growth loops", top_k=3, relevance_cutoff=0.99)
        assert result["chunk_count"] == 0
        assert result["no_relevant_evidence"] is True


class TestRetrievalFilters:
    def test_guest_filter_restricts_episodes(self):
        result = execute_retrieve("positioning against competitors", top_k=3,
                                  guest="April Dunford")
        assert result["chunk_count"] == 3
        assert all(c["guest"] == "April Dunford" for c in result["chunks"])
        assert result["filtered"] == {"guest": "April Dunford"}

    def test_guest_filter_fuzzy_and_case_insensitive(self):
        result = execute_retrieve("LNO framework prioritization", top_k=2,
                                  guest="shreyas")
        assert result["chunk_count"] >= 1
        assert all(c["guest"] == "Shreyas Doshi" for c in result["chunks"])

    def test_guest_filter_matches_ascii_spelling_of_diacritic_names(self):
        # Users and LLMs write 'Alstromer'; the corpus stores 'Alströmer'.
        result = execute_retrieve("growth channels playbook", top_k=2,
                                  guest="Gustaf Alstromer")
        assert result["chunk_count"] >= 1
        assert all(c["guest"] == "Gustaf Alströmer" for c in result["chunks"])

    def test_unknown_guest_returns_filter_error_with_suggestions(self):
        result = execute_retrieve("positioning", top_k=2, guest="Zorpzeb The Unindexed")
        assert "filter_error" in result
        assert "April Dunford" in result["filter_error"]
        assert result["chunk_count"] == 0

    def test_episode_filter_restricts_by_number(self):
        result = execute_retrieve("pmf survey", top_k=3, episode_number=11)
        assert result["chunk_count"] >= 1
        assert all(c["episode_number"] == 11 for c in result["chunks"])

    def test_impossible_episode_yields_empty_not_refusal(self):
        # A valid-but-empty filter is a filter miss, not an off-topic refusal.
        result = execute_retrieve("positioning", top_k=2, episode_number=999)
        assert result["chunk_count"] == 0
        assert "error" in result
        assert "no_relevant_evidence" not in result

    def test_combined_guest_and_episode_filter(self):
        result = execute_retrieve(
            "How does the PMF survey segment customers by expectations?", top_k=3,
            guest="Rahul Vohra", episode_number=11)
        assert result["chunk_count"] >= 1
        assert all(c["guest"] == "Rahul Vohra" and c["episode_number"] == 11
                   for c in result["chunks"])

    def test_unfiltered_refusal_still_works(self):
        result = execute_retrieve("sourdough bread recipe", top_k=2)
        assert result.get("no_relevant_evidence") is True


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
