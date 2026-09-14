"""Groundedness eval runner.

Runs every case in eval_cases.py against the real retrieval pipeline in a
HERMETIC temp Chroma store (fresh index of the committed transcripts), so runs
never touch the dev database and are reproducible in CI.

Scores per case type:
- retrieval: pass if >= min_hits chunks come from expected episodes with top
  score >= min_top_score, no poison-episode chunk appears, and returned
  relevance scores are descending (reranker ordering sanity).
- refusal: pass if no chunks are returned and no_relevant_evidence is set.
- citation: like retrieval, plus the highest-scoring chunk must come from an
  expected episode (the citation pill the UI would show first).

Exit code is nonzero if accuracy drops below --min-accuracy (default 0.9).
"""
import argparse
import logging
import os
import shutil
import sys
import tempfile
from dataclasses import dataclass, field
from typing import List

logging.disable(logging.INFO)  # keep the report readable; re-enabled with --verbose


@dataclass
class CaseResult:
    case_id: str
    kind: str
    query: str
    passed: bool
    detail: str
    cosines: list = field(default_factory=list)


def _build_hermetic_store(tmp_dir: str) -> None:
    """Fresh temp CHROMA_PERSIST_DIRECTORY + re-index from committed transcripts."""
    os.environ["CHROMA_PERSIST_DIRECTORY"] = os.path.join(tmp_dir, "chroma")

    import app.config as config_module
    config_module.settings.CHROMA_PERSIST_DIRECTORY = os.path.join(tmp_dir, "chroma")

    from app.ingestion.ingest import run_ingestion
    res = run_ingestion()
    if res.get("total_chunks", 0) == 0:
        raise RuntimeError("hermetic ingestion produced zero chunks")


def _run_case(case) -> CaseResult:
    from app.agents.tools.retrieve import execute_retrieve

    if case.kind == "refusal":
        res = execute_retrieve(case.query, top_k=4)
        passed = res.get("chunk_count") == 0 and res.get("no_relevant_evidence") is True
        detail = "refused" if passed else (
            f"LEAKED {res.get('chunk_count', 0)} chunks "
            f"{[c['retrieval_score'] for c in res.get('chunks', [])]}"
        )
        return CaseResult(case.case_id, case.kind, case.query, passed, detail)

    res = execute_retrieve(case.query, top_k=6)
    chunks = res.get("chunks", [])
    cosines = [c["retrieval_score"] for c in chunks]

    if not chunks:
        return CaseResult(case.case_id, case.kind, case.query, False,
                          "REFUSED a topical question (gate too tight)", cosines)

    problems = []
    relevance = [c["relevance_score"] for c in chunks]
    if relevance and relevance != sorted(relevance, reverse=True):
        problems.append("scores not descending")

    # The floor applies to the COSINE retrieval score (topical admission), not
    # the reranked score — the cross-encoder legitimately scores topically
    # relevant transcript excerpts near zero.
    top = chunks[0]
    if top["retrieval_score"] < case.min_top_score:
        problems.append(f"top cosine {top['retrieval_score']} < {case.min_top_score}")

    hits = [c for c in chunks if c["episode_number"] in case.expect_episodes]
    if len(hits) < case.min_hits:
        got = sorted({c["episode_number"] for c in chunks})
        problems.append(f"only {len(hits)} hit(s) from {case.expect_episodes}, got episodes {got}")
        return CaseResult(case.case_id, case.kind, case.query, False,
                          "; ".join(problems) or "insufficient hits", cosines)

    if case.poison_episodes:
        poison = [c for c in chunks if c["episode_number"] in case.poison_episodes]
        if poison:
            problems.append(f"poison leak: episodes {sorted({c['episode_number'] for c in poison})}")

    if case.kind == "citation":
        if top["episode_number"] not in case.expect_episodes:
            problems.append(
                f"top citation from ep {top['episode_number']} ({top['guest']}), "
                f"expected {case.expect_episodes}"
            )
        if case.expect_guests and top["guest"] not in case.expect_guests:
            problems.append(f"top guest '{top['guest']}' not in {case.expect_guests}")

    return CaseResult(case.case_id, case.kind, case.query, not problems,
                      "; ".join(problems) or "ok", cosines)


def run_eval(verbose: bool = False) -> dict:
    try:
        from tests.eval.eval_cases import EVAL_CASES
    except ImportError:
        from eval_cases import EVAL_CASES

    tmp_dir = tempfile.mkdtemp(prefix="lenny_eval_")
    try:
        _build_hermetic_store(tmp_dir)
        results: List[CaseResult] = []
        if verbose:
            logging.disable(logging.NOTSET)
        for case in EVAL_CASES:
            results.append(_run_case(case))
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

    total = len(results)
    passed = sum(1 for r in results if r.passed)
    by_kind = {}
    for r in results:
        k = by_kind.setdefault(r.kind, {"total": 0, "passed": 0})
        k["total"] += 1
        k["passed"] += 1 if r.passed else 0

    return {"total": total, "passed": passed, "by_kind": by_kind, "results": results}


def print_report(summary: dict, show_all: bool = False) -> None:
    print("=" * 64)
    print("GROUNDEDNESS EVAL")
    print("=" * 64)
    print(f"overall: {summary['passed']}/{summary['total']} "
          f"({100.0 * summary['passed'] / summary['total']:.1f}%)")
    for kind, k in sorted(summary["by_kind"].items()):
        print(f"  {kind:10} {k['passed']}/{k['total']} "
              f"({100.0 * k['passed'] / k['total']:.1f}%)")

    failures = [r for r in summary["results"] if not r.passed]
    if failures:
        print(f"\n--- FAILURES ({len(failures)}) ---")
        for r in failures:
            print(f"  [{r.kind}] {r.case_id}: {r.detail}")
            print(f"      query: {r.query[:90]}")
            if r.cosines:
                print(f"      cosines: {r.cosines}")
    elif show_all:
        print("\n--- all cases ---")
        for r in summary["results"]:
            print(f"  [{r.kind:9}] {'PASS' if r.passed else 'FAIL'} "
                  f"{r.case_id:22} {r.cosines if r.cosines else r.detail}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the groundedness eval set.")
    parser.add_argument("--min-accuracy", type=float, default=0.9,
                        help="Exit nonzero below this overall accuracy (default 0.9)")
    parser.add_argument("--min-refusal", type=float, default=1.0,
                        help="Exit nonzero below this refusal accuracy (default 1.0)")
    parser.add_argument("--verbose", action="store_true", help="Load models loudly; show all cases with --min-accuracy 0")
    parser.add_argument("--show-all", action="store_true", help="Print every case result")
    args = parser.parse_args()

    if not args.verbose:
        logging.disable(logging.INFO)

    summary = run_eval(verbose=args.verbose)
    print_report(summary, show_all=args.show_all)

    overall = summary["passed"] / summary["total"]
    refusal = (summary["by_kind"].get("refusal", {}).get("passed", 0)
               / max(1, summary["by_kind"].get("refusal", {}).get("total", 1)))
    ok = overall >= args.min_accuracy and refusal >= args.min_refusal
    print(f"\nthresholds: overall>={args.min_accuracy} refusal>={args.min_refusal} -> "
          f"{'OK' if ok else 'BELOW THRESHOLD'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
