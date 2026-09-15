"""
Claude Agent SDK adapter — an alternative agent loop for the assistant.

The app's default loop (agent_manager.AgentManager) drives the tool cycle
directly against whichever provider is selected. This adapter runs the same
job through the **official Anthropic Claude Agent SDK** (claude-agent-sdk):

- The six Lenny tools (retrieve, ship30_essay, artifact_gen, prd_generator,
  pre_mortem, growth_audit) are re-exported as in-process MCP tools via
  ``create_sdk_mcp_server`` — the SDK's recommended way to expose Python
  callables — so both loops share one executor (_execute_tool).
- The SDK subprocess (bundled Claude Code CLI) is pointed at a non-Anthropic
  backend with ``ANTHROPIC_BASE_URL`` + ``ANTHROPIC_AUTH_TOKEN``: Ollama
  exposes an Anthropic-Messages-compatible endpoint at ``/v1/messages``
  (verified live with llama3.2), and an Anthropic API key routes to Claude.
- Events are translated into the exact SSE shapes the default loop yields
  (status / tool_start / tool_end / sources / artifacts / token / done /
  error), so routes and frontend are untouched.
- Any SDK failure (CLI missing, subprocess error, no tool support) raises
  AdapterError and AgentManager falls back to its native loop transparently.

Note on provider support: the SDK targets Claude; routing it to Ollama works
because Ollama implements the Anthropic Messages API. Groq has no such
endpoint, so the adapter is offered for the ollama/anthropic providers only.
"""
import logging
import os
from typing import Any, AsyncGenerator, Dict, List, Optional

from app.config import settings

logger = logging.getLogger("lenny_growth.agent_sdk")

# Reuse the shared tool registry + executor so both loops stay in sync.
from app.agents.agent_manager import SYSTEM_PROMPT, AgentManager  # noqa: E402


class AdapterError(Exception):
    """Raised when the SDK path cannot run; caller falls back to the native loop."""


def sdk_available() -> bool:
    """Whether the SDK path can be attempted at all."""
    try:
        import claude_agent_sdk  # noqa: F401
        return True
    except ImportError:
        return False


def _resolve_routing(provider_type: str) -> Dict[str, str]:
    """Map an app provider to SDK subprocess env + model name.

    Returns env vars to inject into the CLI subprocess (ANTHROPIC_BASE_URL,
    ANTHROPIC_AUTH_TOKEN) and the model identifier it should request.
    """
    if provider_type == "ollama":
        # NOTE: the Claude CLI appends /v1/messages itself, so ANTHROPIC_BASE_URL
        # must be the bare origin — appending /v1 here produces /v1/v1/messages
        # and Ollama 404s (which the CLI misreports as a model error).
        return {
            "ANTHROPIC_BASE_URL": settings.OLLAMA_BASE_URL.rstrip("/"),
            # Ollama ignores the key but the CLI requires a non-empty token.
            "ANTHROPIC_AUTH_TOKEN": "ollama",
            "ANTHROPIC_MODEL": settings.OLLAMA_MODEL,
            "ANTHROPIC_SMALL_FAST_MODEL": settings.OLLAMA_MODEL,
        }
    if provider_type == "anthropic":
        if not settings.ANTHROPIC_API_KEY:
            raise AdapterError("ANTHROPIC_API_KEY is not set")
        return {
            "ANTHROPIC_AUTH_TOKEN": settings.ANTHROPIC_API_KEY,
            "ANTHROPIC_MODEL": settings.ANTHROPIC_MODEL,
            "ANTHROPIC_SMALL_FAST_MODEL": settings.ANTHROPIC_MODEL,
        }
    raise AdapterError(
        f"Provider '{provider_type}' has no Anthropic-Messages-compatible endpoint; "
        "SDK path supports 'ollama' and 'anthropic'."
    )


# ---------------------------------------------------------------------------
# MCP tool wrappers. Built per-turn (not at import) so they close over the
# turn's AgentManager instance — i.e. the same pinned filters, sources and
# artifacts lists the native loop mutates.
# ---------------------------------------------------------------------------

async def _build_mcp_tools(agent: AgentManager, user_message: str,
                           collected_sources: list, generated_artifacts: list,
                           conversation_history: List[Dict[str, Any]]):
    try:
        from claude_agent_sdk import create_sdk_mcp_server, tool
    except ImportError as e:
        raise AdapterError(f"claude-agent-sdk not installed: {e}") from e

    class _ToolCallShim:
        """Duck-types the provider ToolCall shape _execute_tool expects."""

        def __init__(self, name: str, arguments: Dict[str, Any]):
            self.name = name
            self.arguments = arguments
            self.id = f"sdk_{name}"

    async def make_handler(name: str):
        async def handler(args: Dict[str, Any]) -> Dict[str, Any]:
            try:
                out = await agent._execute_tool(
                    _ToolCallShim(name, args),
                    user_message,
                    collected_sources,
                    generated_artifacts,
                    conversation_history,
                )
                return {"content": [{"type": "text", "text": out}]}
            except Exception as e:  # surface tool failure to the model
                logger.error("SDK tool '%s' failed: %s", name, e, exc_info=True)
                return {"content": [{"type": "text", "text": f"Tool error: {e}"}], "isError": True}
        return handler

    tools = []
    for spec in _tool_specs():
        tools.append(tool(
            spec["name"],
            spec["description"],
            spec["input_schema"],
        )(await make_handler(spec["name"])))

    return create_sdk_mcp_server(
        name="lenny-growth-tools",
        version="1.0.0",
        tools=tools,
    )


def _tool_specs() -> List[Dict[str, Any]]:
    """The shared tool registry in the JSON-schema form the SDK expects."""
    from app.agents.tools import AVAILABLE_TOOLS
    specs = []
    for t in AVAILABLE_TOOLS:
        fn = t.get("function", t)
        specs.append({
            "name": fn["name"],
            "description": fn.get("description", ""),
            "input_schema": fn.get("parameters", {"type": "object", "properties": {}}),
        })
    return specs


# ---------------------------------------------------------------------------
# The streaming turn
# ---------------------------------------------------------------------------

async def execute_turn_stream_sdk(
    conversation_history: List[Dict[str, Any]],
    user_message: str,
    retrieve_filters: Optional[Dict[str, Any]] = None,
    provider_type: Optional[str] = None,
) -> AsyncGenerator[Dict[str, Any], None]:
    """Run one agent turn through the Claude Agent SDK, yielding the same
    event shapes as AgentManager.execute_turn_stream. Raises AdapterError
    before yielding anything if the SDK path is not viable."""
    if not sdk_available():
        raise AdapterError("claude-agent-sdk is not installed")

    provider = provider_type or settings.LLM_PROVIDER
    if provider == "mock":
        # The mock engine has no HTTP surface; the native loop handles it.
        raise AdapterError("SDK path not used for the mock provider")

    routing = _resolve_routing(provider)
    model = routing.pop("ANTHROPIC_MODEL", None)
    small_model = routing.pop("ANTHROPIC_SMALL_FAST_MODEL", model)

    from claude_agent_sdk import (
        AssistantMessage,
        ClaudeAgentOptions,
        ResultMessage,
        StreamEvent,
        TextBlock,
        ToolUseBlock,
        query,
    )

    agent = AgentManager(provider_type=provider)
    collected_sources: List[Dict[str, Any]] = []
    generated_artifacts: List[Dict[str, Any]] = []
    mcp_server = await _build_mcp_tools(
        agent, user_message, collected_sources, generated_artifacts,
        conversation_history,
    )

    # Flatten the conversation into the SDK's single-prompt model: the CLI
    # manages its own context, so recent history is serialized as a transcript.
    transcript_lines = []
    for m in conversation_history[-8:]:
        role = "User" if m.get("role") == "user" else "Assistant"
        content = (m.get("content") or "").strip()
        if content:
            transcript_lines.append(f"{role}: {content}")
    prompt = (
        ("Previous conversation:\n" + "\n".join(transcript_lines) + "\n\n")
        if transcript_lines else ""
    ) + f"User: {user_message}"

    options = ClaudeAgentOptions(
        system_prompt=SYSTEM_PROMPT,
        model=model,
        max_turns=12,
        tools=[],  # disable Claude Code's built-in FS/shell tools entirely
        mcp_servers={"lenny": mcp_server},
        allowed_tools=[f"mcp__lenny__{s['name']}" for s in _tool_specs()],
        permission_mode="bypassPermissions",
        include_partial_messages=True,
        env={
            **routing,
            "ANTHROPIC_SMALL_FAST_MODEL": small_model,
            "ANTHROPIC_DEFAULT_HAIKU_MODEL": small_model,
            "ANTHROPIC_DEFAULT_SONNET_MODEL": model or "",
            "ANTHROPIC_DEFAULT_OPUS_MODEL": model or "",
            # Ask the CLI to discover models from {ANTHROPIC_BASE_URL}/v1/models
            # (Ollama serves this list) instead of validating against the
            # hardcoded Anthropic catalog — without it, custom model ids like
            # 'llama3.2' are rejected as "unrecognized".
            "CLAUDE_CODE_ENABLE_GATEWAY_MODEL_DISCOVERY": "1",
            # The CLI appends a context-usage notice as a role:"system" MESSAGE
            # ("<total_tokens>…"). The Anthropic API has no system role inside
            # messages; Ollama's compat layer mishandles it and the local model
            # stops binding tools (emits tool-ish XML instead). Turning the
            # reminder off keeps the message list spec-compliant.
            "CLAUDE_CODE_TOTAL_TOKENS_REMINDER": "0",
            # The CLI also wraps the prompt in a <system-reminder> preamble
            # ("As you answer the user's questions, you can use the following
            # context: … Today's date is …"). Verified via request capture that
            # disabling this carve-slate injection produces a cleaner prompt;
            # harmless for Claude, helpful for small local models.
            "CLAUDE_CODE_CARVED_SLATE": "0",
            "CLAUDE_AGENT_SDK_SKIP_VERSION_CHECK": "1",
            "DISABLE_TELEMETRY": "1",
        },
    )

    yield {"type": "status", "status": "Running the Claude Agent SDK loop..."}

    full_text = ""
    saw_result = False
    tool_names_seen = set()

    try:
        async for message in query(prompt=prompt, options=options):
            if isinstance(message, StreamEvent):
                # StreamEvent wraps a raw Anthropic SSE event; text arrives
                # as content_block_delta / content_block_start payloads.
                payload = getattr(message, "event", None) or getattr(message, "data", None) or {}
                delta = None
                if payload.get("type") == "content_block_delta":
                    d = payload.get("delta", {})
                    if d.get("type") == "text_delta":
                        delta = d.get("text", "")
                elif payload.get("type") == "content_block_start":
                    cb = payload.get("content_block", {})
                    if cb.get("type") == "text":
                        delta = cb.get("text", "") or ""
                if delta:
                    full_text += delta
                    yield {"type": "token", "token": delta}
                continue

            if isinstance(message, AssistantMessage):
                for block in message.content:
                    if isinstance(block, ToolUseBlock):
                        tool_names_seen.add(block.name)
                        yield {"type": "tool_start", "tool": block.name.split("__")[-1]}
                    elif isinstance(block, TextBlock) and block.text:
                        # Non-streaming text (final turn without partials).
                        if not full_text.endswith(block.text):
                            full_text += block.text
                            yield {"type": "token", "token": block.text}

            elif isinstance(message, ResultMessage):
                saw_result = True
    except Exception as e:
        logger.error("Claude Agent SDK turn failed: %s", e, exc_info=True)
        if not full_text and not saw_result:
            raise AdapterError(f"SDK turn failed: {e}") from e
        # Partial output already streamed; report an error event instead.
        yield {"type": "error", "message": f"SDK turn ended early: {e}"}
        return

    if not saw_result and not full_text:
        raise AdapterError("SDK produced no output (is the CLI usable on this platform?)")

    if collected_sources:
        yield {"type": "sources", "sources": collected_sources}
    if generated_artifacts:
        yield {"type": "artifacts", "artifacts": generated_artifacts}

    from app.agents.agent_manager import generate_suggested_follow_ups
    yield {
        "type": "done",
        "full_content": full_text,
        "sources": collected_sources,
        "artifacts": generated_artifacts,
        "follow_ups": generate_suggested_follow_ups(user_message, full_text),
        "provider": f"{provider}+agent-sdk",
        "model": model,
    }
