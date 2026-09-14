"""
Shreyas Doshi Pre-Mortem Simulator Tool.
Anticipates high-risk launch failure modes and formulates prevention plans.
"""
from typing import Dict, Any

PRE_MORTEM_TOOL_SCHEMA = {
    "name": "pre_mortem_simulator",
    "description": "Runs a Shreyas Doshi-style Pre-Mortem on a proposed product launch, feature, or company strategy to uncover hidden failure modes before shipping.",
    "parameters": {
        "type": "object",
        "properties": {
            "initiative_name": {
                "type": "string",
                "description": "The name of the feature, product launch, or growth initiative."
            },
            "launch_context": {
                "type": "string",
                "description": "Brief description of the planned launch and goals."
            },
            "top_failure_modes": {
                "type": "string",
                "description": "Anticipated scenarios where the project fails spectacularly 6 months post-launch."
            }
        },
        "required": ["initiative_name", "launch_context"]
    }
}


def execute_pre_mortem(
    initiative_name: str,
    launch_context: str,
    top_failure_modes: str = ""
) -> Dict[str, Any]:
    content = (
        f"# 🔮 Pre-Mortem Analysis: {initiative_name}\n\n"
        f"> *\"Assume it is 6 months from today, and this launch has been a catastrophic disaster. What went wrong, and how do we prevent it today?\"* — Shreyas Doshi (Ep #78)\n\n"
        f"## 1. Initiative Overview\n"
        f"{launch_context}\n\n"
        f"## 2. Plausible Nightmare Failure Modes\n"
        f"{top_failure_modes if top_failure_modes else '- **Failure Mode 1 (Silent Churn):** Users activate on day 1 but find zero recurring habit value on day 14.\n- **Failure Mode 2 (Cognitive Overload):** Feature introduces UI friction that degrades the core product speed.\n- **Failure Mode 3 (Cross-Functional Desync):** Support and sales teams are not trained on handling edge cases.'}\n\n"
        f"## 3. High-Agency Mitigations & Action Plan\n"
        f"| Failure Risk | Root Cause | Early Warning Indicator | Actionable Prevention Plan |\n"
        f"| :--- | :--- | :--- | :--- |\n"
        f"| **Low D14 Habit Retention** | Lack of closed feedback loop | W1 active users dropping < 40% | Implement automated re-engagement triggers & personalized onboarding |\n"
        f"| **Performance Degrade** | Heavy client-side computation | Latency > 100ms | Enforce strict performance budgets and async background processing |\n"
        f"| **Sales Misalignment** | Ambiguous ICP positioning | High refund / cancellation rate | Mandate 1-page ICP cheat sheet & live demo sessions before launch |\n\n"
        f"## 4. Go / No-Go Pre-Flight Checklist\n"
        f"- [ ] Telemetry & funnel drop-off analytics verified in staging.\n"
        f"- [ ] Rollback flags configured and tested under load.\n"
        f"- [ ] Customer support macro responses and FAQ published.\n"
    )

    return {
        "title": f"Pre-Mortem: {initiative_name}",
        "artifact_type": "pre_mortem",
        "content": content
    }
