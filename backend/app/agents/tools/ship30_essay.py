"""
Ship30/30 Atomic Essay Skill.
"""
import logging
from typing import Dict, Any

logger = logging.getLogger("lenny_growth.tools.ship30_essay")

SHIP30_TOOL_SCHEMA = {
    "name": "ship30_essay",
    "description": "Transforms grounded transcript insights into a high-impact, 250-300 word Ship 30/30 Atomic Essay with a hook, structured subheads, and punchy takeaway.",
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
            }
        },
        "required": ["topic", "core_insights"]
    }
}

SHIP30_SYSTEM_INSTRUCTIONS = """
You are an expert ghostwriter and creator trained in the Ship 30 for 30 Atomic Essay methodology.
Your mission is to transform raw product and growth frameworks from Lenny's Podcast into a polished atomic essay.

STRICT FORMAT RULES:
1. WORD COUNT: Exactly 250 to 300 words. Never exceed 320 words.
2. TITLE: A punchy, magnetic headline (e.g. '# The Marketplace Activation Trap').
3. HOOK (Paragraph 1): 1-2 sentence opening that challenges conventional wisdom or calls out a common mistake.
4. BODY (Sections 1-3): 2 to 3 structured subheadings (###) or bold bullet points delivering high-density, actionable lessons.
5. TAKEAWAY (Final Line): A single bold closing takeaway sentence summarizing the highest-leverage mental model.
6. GROUNDING: Every claim must be grounded in the provided transcript evidence. Do NOT invent concepts.
"""


def execute_ship30_essay(topic: str, core_insights: str, target_audience: str = "Product Managers") -> Dict[str, Any]:
    return {
        "topic": topic,
        "instructions": SHIP30_SYSTEM_INSTRUCTIONS,
        "context": core_insights,
        "target_audience": target_audience,
        "format_target": "ship30_atomic_essay",
        "word_budget": "250-300 words"
    }
