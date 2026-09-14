"""
Startup Growth & Metric Funnel Audit Tool.
Diagnoses drop-offs and leaky bucket problems using Casey Winters & Elena Verna frameworks.
"""
from typing import Dict, Any

GROWTH_AUDIT_TOOL_SCHEMA = {
    "name": "growth_audit",
    "description": "Performs a quantitative and structural growth audit on a startup's funnel, activation rate, or retention curve.",
    "parameters": {
        "type": "object",
        "properties": {
            "business_model": {
                "type": "string",
                "description": "The business model type (e.g., 'B2B SaaS / PLG', 'B2C Marketplace', 'Consumer App', 'E-commerce')."
            },
            "funnel_metrics": {
                "type": "string",
                "description": "User funnel numbers or conversion rates (e.g. 10k visitors -> 500 signups -> 50 activated -> 10 paid)."
            },
            "primary_concern": {
                "type": "string",
                "description": "The primary symptom (e.g., 'High signup drop-off', 'Leaky bucket retention', 'Low PQL conversion')."
            }
        },
        "required": ["business_model", "funnel_metrics"]
    }
}


def execute_growth_audit(
    business_model: str,
    funnel_metrics: str,
    primary_concern: str = "Uncovering funnel drop-offs and growth bottlenecks"
) -> Dict[str, Any]:
    content = (
        f"# 📊 Growth & Metric Funnel Audit\n\n"
        f"**Business Model:** {business_model}\n"
        f"**Audit Focus:** {primary_concern}\n\n"
        f"## 1. Funnel Diagnostic & Benchmarks\n"
        f"**Reported Funnel Data:**\n{funnel_metrics}\n\n"
        f"## 2. Leaky Bucket Analysis (Gustaf Alströmer / Casey Winters Playbook)\n"
        f"- **Top-of-Funnel Conversion:** Assess whether traffic is high-intent vs. empty vanity clicks.\n"
        f"- **Time-to-Value (TTV):** Ensure activation happens in under 5 minutes without requiring a sales call.\n"
        f"- **Cohort Retention Asymptote:** Verify whether your retention curve levels off horizontally or slopes toward zero.\n\n"
        f"## 3. High-Leverage Strategic Interventions\n"
        f"1. **Compress Activation Distance:** Eliminate onboarding steps that do not directly contribute to the user's first 'aha moment'.\n"
        f"2. **Implement PQL Qualification (B2B PLG):** Trigger sales outreach only when a user hits specific product utilization milestones.\n"
        f"3. **Convert Funnels into Closed Loops:** Build viral or content feedback mechanisms where current users automatically bring in the next cohort.\n\n"
        f"## 4. Recommended Growth Experiments for Sprint\n"
        f"- **Experiment A:** Frictionless 1-click template onboarding.\n"
        f"- **Experiment B:** Automated behavioral re-engagement email at D+3 if core activation milestone is incomplete.\n"
    )

    return {
        "title": f"Growth Audit: {business_model}",
        "artifact_type": "growth_audit",
        "content": content
    }
