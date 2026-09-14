"""Pytest entry point: `python -m pytest -m eval` runs the groundedness suite.

These are slow (they load the embedding + reranker models and re-index the
corpus into a temp store), so the `eval` marker is excluded from the default
test run in pytest.ini. CI can add a scheduled/nightly job with `-m eval`.
"""
import pytest

from app.config import settings


@pytest.mark.eval
def test_groundedness_eval_suite():
    from tests.eval.runner import run_eval

    summary = run_eval(verbose=False)

    overall = summary["passed"] / summary["total"]
    refusal = summary["by_kind"].get("refusal", {})
    refusal_rate = refusal.get("passed", 0) / max(1, refusal.get("total", 1))
    retrieval = summary["by_kind"].get("retrieval", {})
    retrieval_rate = retrieval.get("passed", 0) / max(1, retrieval.get("total", 1))

    # Hard gate: refusals must be perfect — a single leak is a real regression.
    assert refusal_rate >= 1.0, f"refusal rate {refusal_rate:.2f} < 1.0"
    # Retrieval may drift a point with model updates; 0.75 guards against rot.
    assert retrieval_rate >= 0.75, f"retrieval rate {retrieval_rate:.2f} < 0.75"
    assert overall >= 0.85, f"overall {overall:.2f} < 0.85"
