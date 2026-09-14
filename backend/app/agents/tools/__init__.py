"""
Agent Tools Package.
"""
from app.agents.tools.retrieve import RETRIEVE_TOOL_SCHEMA, execute_retrieve
from app.agents.tools.ship30_essay import SHIP30_TOOL_SCHEMA, execute_ship30_essay
from app.agents.tools.artifact_gen import ARTIFACT_TOOL_SCHEMA, execute_artifact_gen
from app.agents.tools.prd_generator import PRD_TOOL_SCHEMA, execute_prd_generator
from app.agents.tools.pre_mortem import PRE_MORTEM_TOOL_SCHEMA, execute_pre_mortem
from app.agents.tools.growth_audit import GROWTH_AUDIT_TOOL_SCHEMA, execute_growth_audit

AVAILABLE_TOOLS = [
    RETRIEVE_TOOL_SCHEMA,
    SHIP30_TOOL_SCHEMA,
    ARTIFACT_TOOL_SCHEMA,
    PRD_TOOL_SCHEMA,
    PRE_MORTEM_TOOL_SCHEMA,
    GROWTH_AUDIT_TOOL_SCHEMA,
]
