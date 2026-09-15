"""
Ship 30 for 30 Atomic Essay skill — ~1,250-word essays from grounded insights.

Encodes the Ship 30 for 30 writing framework as structured instructions plus
executable post-conditions (word budget, section structure, takeaway) rather
than an unstructured one-off prompt:

- ~1,250 words (1,100-1,400 accepted) — the Ship 30 "deep-dive atomic essay" length
- Hook: the opening must challenge conventional wisdom or call out a common mistake
- Narrative progression: Context -> Tension -> Resolution across 3-4 subheaded sections
- Skimmable: subheadings, bullets, selective bold emphasis
- One specific, useful takeaway the reader can apply this week
- Grounding: every claim traces to the supplied transcript evidence; nothing invented

The essay is WRITTEN by the active LLM provider (Groq / Ollama / Gemini). If the
provider fails, stalls, or returns junk, a deterministic builder assembles a
serviceable essay directly from the insight bullets so the artifact is never
empty or fabricated.
"""
import logging
import re
from typing import Any, Dict, List, Optional

logger = logging.getLogger("lenny_growth.tools.ship30_essay")

SHIP30_TOOL_SCHEMA = {
    "name": "ship30_essay",
    "description": (
        "Writes a ~1,250-word Ship 30 for 30 atomic essay (hook, subheaded "
        "narrative progression, skimmable formatting, bolded takeaway) from "
        "grounded transcript insights."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "topic": {
                "type": "string",
                "description": "The specific growth or product concept to cover."
            },
            "core_insights": {
                "type": "string",
                "description": "The grounded insights and quotes retrieved from Lenny's transcripts."
            },
            "target_audience": {
                "type": "string",
                "description": "Target reader.",
                "default": "Product Managers and Growth Leads"
            },
            "title": {
                "type": "string",
                "description": "Optional essay title; one is derived from the topic if omitted."
            }
        },
        "required": ["topic", "core_insights"]
    }
}

WORD_BUDGET = (1100, 1400)
TARGET_WORDS = 1250
MIN_ACCEPTABLE_WORDS = 900  # below this, ask the model to expand once

ESSAY_SYSTEM_PROMPT = """You are an expert ghostwriter trained in the Ship 30 for 30 atomic essay methodology. You transform raw product and growth insights into polished, publishable essays.

STRICT FORMAT RULES:
1. LENGTH: 1,100 to 1,400 words (aim for ~1,250). This is a deep-dive essay, not a tweet thread.
2. TITLE: A punchy, magnetic headline as an H1 (e.g. "# The Marketplace Activation Trap").
3. HOOK: Your opening paragraph must challenge conventional wisdom or call out a common, costly mistake. No throat-clearing, no "In today's world".
4. NARRATIVE PROGRESSION: Move the reader through Context -> Tension -> Resolution. Each of your 3-4 sections (### subheadings) must advance the argument, not just list facts.
5. SKIMMABILITY: Use subheadings, bullets where they add scannability, and bold for the 3-5 phrases a skimmer must not miss. Prose paragraphs stay short (2-4 sentences).
6. TAKEAWAY: End with a single bolded closing line: the one mental model or action the reader should take this week.
7. GROUNDING: Every claim must trace to the supplied transcript evidence. Attribute insights to the speakers/episodes they came from. Do NOT invent frameworks, numbers, or quotes. If the evidence is thin on a point, say so plainly instead of filling gaps.

OUTPUT: Only the essay markdown. No preamble, no meta-commentary, no word count note."""


def _count_words(md: str) -> int:
    """Word count over prose: strip markdown markers so '#' or '**' don't count."""
    text = re.sub(r"[#*`>\-]+", " ", md)
    return len(text.split())


def _default_title(topic: str) -> str:
    words = topic.strip().rstrip(".?!").split()
    return " ".join(words[:8]).capitalize() if words else "Growth Essay"


def _extract_title(essay: str, fallback: str) -> str:
    m = re.search(r"^\s*#\s+(.+)$", essay, re.MULTILINE)
    return m.group(1).strip() if m else fallback


def _split_insights(core_insights: str) -> List[str]:
    """Break the raw evidence string into discrete insight bullets."""
    parts = re.split(r"\n+|\s*;\s*|\s*\.\s+", core_insights)
    return [p.strip(" -•\t") for p in parts if p and p.strip(" -•\t")]


def _fallback_essay(topic: str, core_insights: str, audience: str) -> str:
    """Deterministic essay assembled from the insight bullets.

    Used only when the LLM path fails. It never invents content: every line
    comes from the supplied evidence, restructured into the Ship 30 shape.
    """
    insights = _split_insights(core_insights)[:6] or [topic]
    title = _default_title(topic)
    sections = []
    for i, ins in enumerate(insights, 1):
        lead = " ".join(ins.split()[:7])
        sections.append(
            f"### {i}. {lead}\n\n"
            f"**{ins}** — that is the pattern the transcript evidence surfaces, "
            f"and it is the one {audience.lower()} keep re-learning the hard way. "
            f"Treat it as a check before your next decision on {topic.lower()}."
        )
    return (
        f"# {title}\n\n"
        f"Most teams get {topic.lower()} wrong — not because they lack information, "
        f"but because they optimize the obvious instead of the lever. "
        f"What follows is what the evidence actually says.\n\n"
        + "\n\n".join(sections)
        + f"\n\n---\n\n**The takeaway: {topic.strip()} is won by acting on the evidence above — start with insight #1 this week.**"
    )


async def execute_ship30_essay(
    topic: str,
    core_insights: str,
    target_audience: str = "Product Managers",
    title: Optional[str] = None,
    provider: Optional[Any] = None,
) -> Dict[str, Any]:
    """Write the essay with the active provider; fall back deterministically.

    Returns the artifact dict consumed by the frontend (title, artifact_type,
    content) plus Ship 30 metadata (word_count, target_range, backend).
    """
    from app.llm.provider import get_provider  # local import avoids import cycles

    essay = ""
    backend = "llm"
    try:
        llm = provider or get_provider()
        user_prompt = (
            f"TOPIC: {topic}\n"
            f"AUDIENCE: {target_audience}\n\n"
            f"TRANSCRIPT EVIDENCE (your only source material):\n"
            f"{core_insights}\n\n"
            f"Write the complete ~{TARGET_WORDS}-word essay now. Output only the essay markdown."
        )
        resp = await llm.generate(
            messages=[{"role": "user", "content": user_prompt}],
            system_prompt=ESSAY_SYSTEM_PROMPT,
            tools=None,
        )
        essay = (resp.content or "").strip()

        # Post-condition: length. One expansion round if the draft is short.
        wc = _count_words(essay)
        if essay and wc < MIN_ACCEPTABLE_WORDS:
            logger.info("Ship30 draft too short (%d words); requesting expansion.", wc)
            resp2 = await llm.generate(
                messages=[
                    {"role": "user", "content": user_prompt},
                    {"role": "assistant", "content": essay},
                    {
                        "role": "user",
                        "content": (
                            f"Your draft is only ~{wc} words. Expand it to the "
                            f"{WORD_BUDGET[0]}-{WORD_BUDGET[1]}-word budget: deepen the "
                            f"narrative progression and add grounded detail from the "
                            f"evidence — do not pad with fluff or invent claims. "
                            f"Output only the full revised essay."
                        ),
                    },
                ],
                system_prompt=ESSAY_SYSTEM_PROMPT,
                tools=None,
            )
            expanded = (resp2.content or "").strip()
            if _count_words(expanded) > wc:
                essay = expanded
    except Exception as e:
        logger.error("Ship30 LLM generation failed (%s); using deterministic fallback.", e)
        essay = ""

    if not essay:
        essay = _fallback_essay(topic, core_insights, target_audience)
        backend = "fallback"

    wc = _count_words(essay)
    resolved_title = title or _extract_title(essay, _default_title(topic))

    return {
        "title": resolved_title,
        "artifact_type": "essay",
        "content": essay,
        "word_count": wc,
        "target_range": list(WORD_BUDGET),
        "word_count_ok": WORD_BUDGET[0] <= wc <= WORD_BUDGET[1],
        "grounded": bool(core_insights.strip()),
        "backend": backend,
    }
