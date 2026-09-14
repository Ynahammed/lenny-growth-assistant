"""
Product Requirement Document (PRD) Generator Tool.
Formats complete, battle-tested PRDs using Lenny's community standard.
"""
from typing import Dict, Any

PRD_TOOL_SCHEMA = {
    "name": "prd_generator",
    "description": "Generates a structured, production-grade Product Requirements Document (PRD) for a new feature, product, or growth experiment.",
    "parameters": {
        "type": "object",
        "properties": {
            "title": {
                "type": "string",
                "description": "The title of the product feature or initiative."
            },
            "problem_statement": {
                "type": "string",
                "description": "The core user problem, struggling moment (JTBD), and business context."
            },
            "target_persona": {
                "type": "string",
                "description": "The High-Expectation Customer (HXC) or Ideal Customer Profile (ICP)."
            },
            "goals_and_metrics": {
                "type": "string",
                "description": "The North Star metric, primary input metrics, and guardrail metrics."
            },
            "user_stories": {
                "type": "string",
                "description": "Key user stories / functional requirements in 'As a user, I want X so that Y' format."
            },
            "non_goals": {
                "type": "string",
                "description": "Explicit out-of-scope items to prevent scope creep."
            }
        },
        "required": ["title", "problem_statement"]
    }
}


def execute_prd_generator(
    title: str,
    problem_statement: str,
    target_persona: str = "High-Expectation Product User",
    goals_and_metrics: str = "Increase 30-day cohort retention and time-to-value",
    user_stories: str = "Core workflow optimization and frictionless UX",
    non_goals: str = "Enterprise custom integrations in v1"
) -> Dict[str, Any]:
    prd_markdown = (
        f"# 📄 PRD: {title}\n\n"
        f"**Status:** Draft | **Author:** Lenny Growth Assistant | **Version:** 1.0\n\n"
        f"## 1. Problem Statement & Struggling Moment\n"
        f"{problem_statement}\n\n"
        f"## 2. Target Customer Profile (ICP / HXC)\n"
        f"{target_persona}\n\n"
        f"## 3. Goals & Key Success Metrics\n"
        f"- **Primary / North Star Metric:** {goals_and_metrics}\n"
        f"- **Guardrail Metric:** User satisfaction, churn rate, sub-100ms interaction latency.\n\n"
        f"## 4. User Stories & Functional Scope\n"
        f"{user_stories}\n\n"
        f"## 5. Explicit Non-Goals (Scope Fence)\n"
        f"{non_goals}\n\n"
        f"## 6. Rollout & Validation Plan\n"
        f"- **Phase 1 (Alpha):** 5% internal / high-agency cohort testing with qualitative feedback.\n"
        f"- **Phase 2 (Beta):** A/B experiment measuring activation milestone completion.\n"
        f"- **Phase 3 (GA):** Full rollout with real-time error telemetry and retention monitoring.\n"
    )

    return {
        "title": f"PRD: {title}",
        "artifact_type": "prd",
        "content": prd_markdown
    }
