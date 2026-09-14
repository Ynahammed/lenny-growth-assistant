"""
Query contextualization: rewrite vague follow-up questions into self-contained
search queries before embedding them.

A bare follow-up like "what about retention?" embeds poorly on its own — the
bi-encoder has no idea retention *of what*. Before retrieval, the recent
conversation is used to rewrite it into "how do I improve user retention for a
B2B SaaS product after Product-Market Fit?".

Design:
- Only vague queries pay the rewrite cost; self-contained questions skip it.
- The rewriter is the configured LLM with a strict prompt (return ONLY the
  rewritten query). Any failure falls back to a deterministic heuristic:
  last user message + the follow-up, so retrieval always gets something
  better than the bare fragment.
"""
import logging
import re
from typing import List, Dict, Any, Optional

logger = logging.getLogger("lenny_growth.rag.query_rewrite")

REWRITE_SYSTEM_PROMPT = """You rewrite follow-up questions into self-contained search queries.

Given a conversation and a follow-up question, output ONE search query that:
- Resolves every pronoun and vague reference using the conversation context
- Stands alone: someone reading only the rewritten query understands it
- Keeps the follow-up's actual intent (does not answer it, does not add topics
  the user did not ask about)
- Is a question or keyword query, under 40 words

Output ONLY the rewritten query text. No quotes, no explanation, no preamble."""

# Follow-ups that look like these almost certainly need context to be
# searchable. Checked against the raw follow-up text.
_VAGUE_PATTERNS = [
    r"^what about\b",
    r"^and what about\b",
    r"^how about\b",
    r"^why\b(?! (is|do|does|are|the)\b.{15,})",  # bare "why?" style
    r"^what (else|then)\b",
    r"^tell me more\b",
    r"^go (deeper|on)\b",
    r"^more (on|about|detail)\b",
    r"^elaborate\b",
    r"^expand\b",
    r"^explain (more|that|this|further)\b",
    r"^that\b",
    r"^this\b",
    r"^it\b",
    r"^those\b",
    r"^these\b",
    r"^(his|her|their|its) ",
    r"^(he|she|they) ",
    r"^(the|that) (first|second|third|last) (one|point|step|idea)",
    r"\b(that|this) (framework|approach|strategy|metric|method|tactic)\b",
    r"^(can you|could you) (elaborate|expand|clarify|go deeper)\b",
    r"^(any|some) (examples|tips|resources)\b",
    r"^(what|which) (one|ones)\b",
    r"^(how) (so|come)\b",
    r"^(sure|ok|okay|interesting|got it)\b.{0,10}$",
    r"^(and|but) (how|what|why)\b",
    r"^(source|citation)s?\b",
    r"^(example|examples)\b",
]

# Minimum word count under which a query is treated as a fragment.
_MIN_WORDS = 4

_MAX_HISTORY_TURNS = 6  # user+assistant message pairs kept for the rewrite prompt


def is_vague_query(query: str) -> bool:
    """Heuristic: does this query need conversation context to be searchable?"""
    q = (query or "").strip().lower()
    if not q:
        return True
    if len(q.split()) < _MIN_WORDS and len(q) < 40:
        return True
    return any(re.search(p, q) for p in _VAGUE_PATTERNS)


def _format_history(history: List[Dict[str, Any]]) -> str:
    lines = []
    for m in history[-_MAX_HISTORY_TURNS * 2:]:
        role = "User" if m.get("role") == "user" else "Assistant"
        content = (m.get("content") or "").strip().replace("\n", " ")
        if content:
            lines.append(f"{role}: {content[:400]}")
    return "\n".join(lines)


def build_fallback_query(query: str, history: List[Dict[str, Any]]) -> str:
    """Deterministic context stitching used when the LLM rewriter fails or is
    unavailable: last user message + the follow-up fragment."""
    last_user = next(
        (m.get("content", "") for m in reversed(history) if m.get("role") == "user"),
        "",
    ).strip().replace("\n", " ")
    if last_user and last_user.lower() != query.strip().lower():
        return f"{last_user} — {query.strip()}"
    return query.strip()


async def rewrite_query_for_search(
    query: str,
    conversation_history: List[Dict[str, Any]],
    provider: Any = None,
) -> Dict[str, Any]:
    """Return {"query": <search query>, "rewritten": bool, "method": str}.

    Skips the LLM entirely for self-contained queries; falls back to
    deterministic stitching when the provider errors, stalls, or returns junk.
    """
    history = list(conversation_history or [])
    if not history or not is_vague_query(query):
        return {"query": query, "rewritten": False, "method": "self_contained"}

    fallback = build_fallback_query(query, history)

    if provider is None:
        return {"query": fallback, "rewritten": True, "method": "fallback"}

    prompt = (
        f"Conversation:\n{_format_history(history)}\n\n"
        f"Follow-up question: {query}\n\n"
        "Rewritten self-contained search query:"
    )
    try:
        response = await provider.generate(
            messages=[{"role": "user", "content": prompt}],
            system_prompt=REWRITE_SYSTEM_PROMPT,
            tools=None,
        )
        rewritten = (response.content or "").strip().strip('"').strip()
        if (
            not rewritten
            or len(rewritten) < 3
            or len(rewritten) > 400
            or rewritten.lower().startswith(("here", "sure", "rewritten"))
            or "\n" in rewritten
        ):
            logger.info(f"Rewriter returned unusable output for '{query}'; using fallback")
            return {"query": fallback, "rewritten": True, "method": "fallback"}
        logger.info(f"Query contextualized: '{query}' -> '{rewritten}'")
        return {"query": rewritten, "rewritten": True, "method": "llm"}
    except Exception as e:
        logger.warning(f"Query rewrite failed ({e}); using deterministic fallback")
        return {"query": fallback, "rewritten": True, "method": "fallback"}
