"""Groundedness eval set: known Q&A pairs asserting what the RAG pipeline must do.

Three case types:
- retrieval: on-topic question -> must return >= min_hits chunks from the
  expected episode(s) above the relevance floor, and must NOT leak chunks from
  a "poison" episode that is topically unrelated to the question.
- refusal: off-domain question -> must return no_relevant_evidence with zero
  chunks (the LLM refusal prompt is downstream of this signal).
- citation: question plus expected guest(s) -> the cited sources for the
  correct episode must outrank everything else in the returned pool.

Numbers are calibrated against the live corpus (bge-small embeddings,
ms-marco MiniLM reranker, RELEVANCE_CUTOFF=0.62). Re-run scripts/eval_rag.py
after any retrieval change; treat regressions > a few points as breakage.
"""
from typing import List, Optional

RETRIEVAL_FLOOR = 0.62  # matches settings.RELEVANCE_CUTOFF default


class EvalCase:
    def __init__(
        self,
        case_id: str,
        kind: str,
        query: str,
        expect_episodes: Optional[List[int]] = None,
        expect_guests: Optional[List[str]] = None,
        poison_episodes: Optional[List[int]] = None,
        min_hits: int = 2,
        min_top_score: float = RETRIEVAL_FLOOR,
    ):
        self.case_id = case_id
        self.kind = kind  # "retrieval" | "refusal" | "citation"
        self.query = query
        self.expect_episodes = expect_episodes or []
        self.expect_guests = expect_guests or []
        self.poison_episodes = poison_episodes or []
        self.min_hits = min_hits
        self.min_top_score = min_top_score


EVAL_CASES = [
    # ---------- retrieval: on-topic questions must surface the right episodes ----------
    EvalCase("pmf_survey", "retrieval",
             "How did Rahul Vohra measure product-market fit at Superhuman?",
             expect_episodes=[11], expect_guests=["Rahul Vohra"],
             poison_episodes=[104], min_hits=2),
    EvalCase("lno_framework", "retrieval",
             "What is Shreyas Doshi's LNO framework for task management?",
             expect_episodes=[78], expect_guests=["Shreyas Doshi"],
             poison_episodes=[100], min_hits=2),
    EvalCase("growth_loops", "retrieval",
             "What is the difference between growth loops and linear funnels?",
             expect_episodes=[42], expect_guests=["Casey Winters"],
             poison_episodes=[104], min_hits=2),
    EvalCase("activation_metric", "retrieval",
             "How should a marketplace define its activation metric?",
             expect_episodes=[42, 100], min_hits=1),
    EvalCase("positioning", "retrieval",
             "How do I position my product against competitive alternatives?",
             expect_episodes=[104], expect_guests=["April Dunford"],
             poison_episodes=[42], min_hits=2),
    EvalCase("jtbd_forces", "retrieval",
             "What are the four forces of progress in Jobs-to-be-Done?",
             expect_episodes=[91], expect_guests=["Bob Moesta"],
             poison_episodes=[104], min_hits=1),
    EvalCase("b2b_plg", "retrieval",
             "How is B2B product-led growth different from B2C PLG?",
             expect_episodes=[95], expect_guests=["Elena Verna"],
             poison_episodes=[100], min_hits=1),
    EvalCase("north_star", "retrieval",
             "How do I choose the right North Star metric for my product?",
             expect_episodes=[11, 78], min_hits=1),
    EvalCase("retention", "retrieval",
             "How do I improve user retention in a SaaS product?",
             expect_episodes=[52, 42, 95], min_hits=1),
    EvalCase("cold_start", "retrieval",
             "How do marketplaces solve the cold start problem?",
             expect_episodes=[100], expect_guests=["Lenny Rachitsky"],
             poison_episodes=[104], min_hits=1),
    EvalCase("yc_growth", "retrieval",
             "What does the Y Combinator growth playbook say about picking channels?",
             expect_episodes=[52], expect_guests=["Gustaf Alströmer"],
             min_hits=1),
    EvalCase("founder_led", "retrieval",
             "What is founder-led product development according to Brian Chesky?",
             expect_episodes=[110], expect_guests=["Brian Chesky"],
             poison_episodes=[52], min_hits=1),
    EvalCase("leading_lagging", "retrieval",
             "What is the difference between leading and lagging indicators?",
             expect_episodes=[11, 78], min_hits=1),
    EvalCase("hxc_segment", "retrieval",
             # KNOWN GAP: jargon phrasing scores 0.602 vs the 0.62 gate (the
             # off-topic ceiling is 0.579, so the gate cannot be lowered).
             # Adding PMF-survey context lifts it to 0.659 and it passes.
             "What are high-expectation customers and how do you identify them?",
             expect_episodes=[11], expect_guests=["Rahul Vohra"],
             min_hits=1),
    EvalCase("positioning_vs_category", "retrieval",
             "When should you choose a new market category versus positioning within one?",
             expect_episodes=[104], expect_guests=["April Dunford"],
             min_hits=1),
    EvalCase("jtbd_typo", "retrieval",
             "explian the jobs to be done framework for understandng customer motivation",
             expect_episodes=[91], expect_guests=["Bob Moesta"],
             min_hits=1),
    EvalCase("pmf_paraphrase", "retrieval",
             "how can I tell if people would be really sad if my product disappeared?",
             expect_episodes=[11], expect_guests=["Rahul Vohra"],
             min_hits=1),

    # ---------- refusal: off-domain questions must produce zero chunks ----------
    EvalCase("refuse_cooking", "refusal",
             "What is the best sourdough bread recipe?"),
    EvalCase("refuse_sports", "refusal",
             "Who won the football game yesterday?"),
    EvalCase("refuse_code", "refusal",
             "Write me a python web scraper using requests and beautifulsoup."),
    EvalCase("refuse_weather", "refusal",
             "What's the weather forecast for tomorrow in San Francisco?"),
    EvalCase("refuse_history", "refusal",
             "Summarize the causes of World War I."),
    EvalCase("refuse_medical", "refusal",
             "What are the side effects of ibuprofen?"),
    EvalCase("refuse_gibberish", "refusal",
             "xqzt vvv plk mnqw zzzz frobnicate the wibble."),
    EvalCase("refuse_travel", "refusal",
             "What are the best hotels in Paris for a family vacation?"),
    EvalCase("refuse_crypto", "refusal",
             "Should I invest in dogecoin right now?"),
    EvalCase("refuse_movie", "refusal",
             "What was the plot of the movie Inception?"),

    # ---------- citation: correct-episode sources must outrank the rest ----------
    EvalCase("cite_pmf", "citation",
             "How did Rahul Vohra measure product-market fit at Superhuman?",
             expect_guests=["Rahul Vohra"], expect_episodes=[11], poison_episodes=[104]),
    EvalCase("cite_loops", "citation",
             "Explain growth loops versus funnels with Casey Winters.",
             expect_guests=["Casey Winters"], expect_episodes=[42], poison_episodes=[104]),
    EvalCase("cite_positioning", "citation",
             "How does April Dunford recommend doing product positioning?",
             expect_guests=["April Dunford"], expect_episodes=[104], poison_episodes=[42]),
    EvalCase("cite_lno", "citation",
             "Break down Shreyas Doshi's LNO prioritization approach.",
             expect_guests=["Shreyas Doshi"], expect_episodes=[78], poison_episodes=[100]),
    EvalCase("cite_moesta", "citation",
             "How does Bob Moesta think about customer motivation and anxiety?",
             expect_guests=["Bob Moesta"], expect_episodes=[91], poison_episodes=[104]),
    EvalCase("cite_verna", "citation",
             "What does Elena Verna say about B2B product-led growth?",
             expect_guests=["Elena Verna"], expect_episodes=[95], poison_episodes=[100]),
]
