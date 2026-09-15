"""
Agent Manager & Multi-Tool Orchestration Engine with Streaming Support.
"""
import logging
import asyncio
from typing import List, Dict, Any, Optional, AsyncGenerator
from app.config import settings
from app.llm.provider import get_provider, LLMProvider, LLMResponse
from app.agents.tools import AVAILABLE_TOOLS
from app.agents.tools.retrieve import execute_retrieve
from app.agents.tools.ship30_essay import execute_ship30_essay
from app.agents.tools.artifact_gen import execute_artifact_gen
from app.agents.tools.prd_generator import execute_prd_generator
from app.agents.tools.pre_mortem import execute_pre_mortem
from app.agents.tools.growth_audit import execute_growth_audit
from app.rag.query_rewrite import rewrite_query_for_search

logger = logging.getLogger("lenny_growth.agents.manager")

SYSTEM_PROMPT = """
You are the Lenny Growth Assistant, an AI expert trained exclusively on transcripts from Lenny's Podcast and Newsletter.
You provide precise, battle-tested advice for Product Managers, Growth Leads, and Founders.

CORE OPERATING PRINCIPLES:
1. STRICT TRANSCRIPT GROUNDING:
   - Answer questions using evidence from Lenny's podcast transcript corpus.
   - Cite your sources clearly with the guest name and episode (e.g. "According to Casey Winters in Ep #42...").

2. EXPLICIT REFUSAL ON UNGROUNDED QUERIES:
   - The retrieve tool already filters out low-relevance matches and reports
     `no_relevant_evidence: true` when nothing clears the threshold. When that
     flag is set (or no transcripts are found), you MUST explicitly refuse:
     "I couldn't find any discussion about this topic in Lenny's podcast transcript corpus. I only provide insights grounded in Lenny's podcast episodes."
   - NEVER answer off-topic questions from general knowledge, and NEVER invent
     citations or guests. No evidence means refusal — not a best guess.

3. SPECIALIZED PRODUCT TOOLS:
   - Use `prd_generator` when asked for a PRD, product spec, or feature requirements.
   - Use `pre_mortem_simulator` when asked for a Pre-Mortem or launch failure risk analysis.
   - Use `growth_audit` when analyzing funnel metrics, churn, or retention drop-offs.
   - Use `ship30_essay` when asked for an atomic essay or publishable summary.

4. OPTIONAL RETRIEVAL FILTERS:
   - `retrieve` accepts optional `guest` and `episode_number` arguments. When the
     user names a guest ('what does Shreyas say...') or a specific episode
     ('in episode 64...'), pass the filter. If a `filter_error` names available
     guests, retry once with a corrected guest name from that list.
"""


def generate_suggested_follow_ups(user_message: str, response_text: str) -> List[str]:
    """Generates 2-3 contextual follow-up prompt pills based on the response content."""
    text_lower = (user_message + " " + response_text).lower()
    
    if "lno" in text_lower or "shreyas" in text_lower:
        return [
            "How do I run a Shreyas Doshi Pre-Mortem before launch?",
            "What does 'high-agency' mean in product management?",
            "Write a Ship30 essay on LNO task prioritization."
        ]
    elif "pmf" in text_lower or "superhuman" in text_lower or "rahul" in text_lower:
        return [
            "How does Rahul Vohra segment High-Expectation Customers (HXC)?",
            "What is the 100ms rule for product speed?",
            "Generate a PRD for a customer onboarding experiment."
        ]
    elif "retention" in text_lower or "gustaf" in text_lower or "yc" in text_lower:
        return [
            "How do I choose the right North Star Metric?",
            "Audit my B2B SaaS signup funnel drop-offs.",
            "Explain growth loops vs linear funnels by Casey Winters."
        ]
    elif "jtbd" in text_lower or "moesta" in text_lower:
        return [
            "How do you reduce customer Anxiety during onboarding?",
            "What are the 4 Forces of Progress in JTBD?",
            "Create a PRD using Jobs-to-be-Done principles."
        ]
    elif "casey" in text_lower or "activation" in text_lower or "loop" in text_lower:
        return [
            "What is the difference between supply-side and demand-side activation?",
            "What question determines if you have a real growth loop?",
            "Write a Ship30 atomic essay on modern marketplace activation."
        ]
    else:
        return [
            "Explain Shreyas Doshi's LNO framework for PM time management.",
            "How does Rahul Vohra measure Product-Market Fit quantitatively?",
            "What are the 3 pillars of B2B Product-Led Growth?"
        ]


class AgentManager:
    """Manages conversational agent execution, multi-tool calling, citations, and streaming."""

    def __init__(self, provider_type: Optional[str] = None):
        self.provider_type = provider_type or settings.LLM_PROVIDER
        self.provider: LLMProvider = get_provider(self.provider_type)
        # Per-turn retrieval filters (set by routes from UI filter chips).
        self._turn_filters: Dict[str, Any] = {}

    async def _execute_tool(self, tool_call, user_message: str, collected_sources: list, generated_artifacts: list, conversation_history: Optional[List[Dict[str, Any]]] = None) -> str:
        name = tool_call.name
        args = tool_call.arguments
        logger.info(f"Agent executing tool '{name}' with args: {args}")

        if name == "retrieve":
            query = args.get("query") or args.get("q") or args.get("topic") or user_message
            if isinstance(query, (int, float)):
                query = user_message
            top_k = args.get("top_k", settings.TOP_K_RETRIEVAL)
            if not isinstance(top_k, int):
                top_k = settings.TOP_K_RETRIEVAL
            # UI-supplied turn filters express explicit user intent and WIN
            # over whatever guest/episode the LLM puts in its tool args.
            guest = self._turn_filters.get("guest") or args.get("guest")
            if isinstance(guest, str) and not guest.strip():
                guest = None
            episode_number = self._turn_filters.get("episode_number")
            if episode_number is None:
                episode_number = args.get("episode_number")
            if isinstance(episode_number, str):
                try:
                    episode_number = int(episode_number)
                except (TypeError, ValueError):
                    episode_number = None
            if not isinstance(episode_number, int):
                episode_number = None
            # Contextualize vague follow-ups ("what about retention?") into
            # self-contained search queries before embedding.
            search_query = str(query)
            rewrite = await rewrite_query_for_search(
                search_query, conversation_history or [], provider=self.provider,
            )
            if rewrite["rewritten"]:
                search_query = rewrite["query"]

            retrieval_res = execute_retrieve(
                query=search_query, top_k=top_k,
                guest=guest, episode_number=episode_number,
            )
            if rewrite["rewritten"]:
                retrieval_res["original_query"] = str(query)

            for chunk in retrieval_res.get("chunks", []):
                if not any(s.get("chunk_id") == chunk.get("chunk_id") for s in collected_sources):
                    collected_sources.append(chunk)

            formatted_chunks = []
            for idx, ch in enumerate(retrieval_res.get("chunks", []), 1):
                formatted_chunks.append(
                    f"[{idx}] GUEST: {ch['guest']} | EPISODE: {ch['episode_title']} (Ep #{ch['episode_number']})\n"
                    f"EXCERPT: {ch['excerpt']}\n"
                )
            if retrieval_res.get("no_relevant_evidence"):
                return (
                    "NO_RELEVANT_EVIDENCE: no transcript chunks met the relevance "
                    "threshold for this query. Per your instructions, you MUST refuse "
                    "to answer this topic from general knowledge."
                )
            if retrieval_res.get("filter_error"):
                return f"FILTER_ERROR: {retrieval_res['filter_error']} Retry the retrieve call with a valid guest from the list above, or without the filter."
            return "\n---\n".join(formatted_chunks) if formatted_chunks else "No relevant transcripts found."

        elif name == "prd_generator":
            title = args.get("title", "Growth Feature PRD")
            prob = args.get("problem_statement", user_message)
            persona = args.get("target_persona", "High-Expectation Customer")
            goals = args.get("goals_and_metrics", "Increase D30 Retention and Time-to-Value")
            stories = args.get("user_stories", "Core user onboarding & activation flow")
            non_goals = args.get("non_goals", "Custom enterprise integrations in v1")
            
            art = execute_prd_generator(title=title, problem_statement=prob, target_persona=persona, goals_and_metrics=goals, user_stories=stories, non_goals=non_goals)
            generated_artifacts.append(art)
            return f"PRD '{title}' generated successfully."

        elif name == "pre_mortem_simulator":
            init = args.get("initiative_name", "Feature Launch")
            ctx = args.get("launch_context", user_message)
            modes = args.get("top_failure_modes", "")
            art = execute_pre_mortem(initiative_name=init, launch_context=ctx, top_failure_modes=modes)
            generated_artifacts.append(art)
            return f"Pre-Mortem for '{init}' conducted and rendered."

        elif name == "growth_audit":
            bm = args.get("business_model", "B2B SaaS / PLG")
            metrics = args.get("funnel_metrics", user_message)
            concern = args.get("primary_concern", "Funnel drop-offs and retention leaks")
            art = execute_growth_audit(business_model=bm, funnel_metrics=metrics, primary_concern=concern)
            generated_artifacts.append(art)
            return f"Growth Audit for '{bm}' completed."

        elif name == "ship30_essay":
            topic = args.get("topic", user_message)
            insights = args.get("core_insights", "")
            target_aud = args.get("target_audience", "Product Managers")
            essay_title = args.get("title")
            # The essay is WRITTEN here by the active provider (Ship 30 for 30
            # framework, ~1,250 words) and returned as a ready artifact.
            art = await execute_ship30_essay(
                topic=topic, core_insights=insights, target_audience=target_aud,
                title=essay_title, provider=self.provider,
            )
            generated_artifacts.append(art)
            return (
                f"Ship30 atomic essay '{art['title']}' generated "
                f"({art['word_count']} words, backend={art['backend']}). "
                "Summarize for the user and point them to the essay artifact."
            )

        elif name == "artifact_gen":
            title = args.get("title", "Generated Growth Artifact")
            art_type = args.get("artifact_type", "markdown")
            content = args.get("content", "")
            art_res = execute_artifact_gen(title=title, artifact_type=art_type, content=content)
            generated_artifacts.append(art_res)
            return f"Artifact '{title}' created."

        return "Tool completed."

    async def execute_turn(
        self,
        conversation_history: List[Dict[str, Any]],
        user_message: str,
        max_tool_iterations: int = 3,
        retrieve_filters: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        messages = list(conversation_history)
        messages.append({"role": "user", "content": user_message})

        collected_sources: List[Dict[str, Any]] = []
        generated_artifacts: List[Dict[str, Any]] = []
        tool_results_history = list(messages)
        self._turn_filters = dict(retrieve_filters) if retrieve_filters else {}

        for iteration in range(max_tool_iterations):
            current_tools = None if (collected_sources or iteration > 0) else AVAILABLE_TOOLS
            try:
                response: LLMResponse = await self.provider.generate(
                    messages=tool_results_history,
                    system_prompt=SYSTEM_PROMPT,
                    tools=current_tools
                )
            except Exception as e:
                logger.error(f"LLM Provider error: {e}", exc_info=True)
                return {
                    "role": "assistant",
                    "content": f"⚠️ Communication error with model provider ({self.provider.provider_name}): {str(e)}",
                    "sources": [],
                    "artifacts": [],
                    "follow_ups": [],
                    "provider": self.provider.provider_name,
                    "model": self.provider.model_name
                }

            if not response.tool_calls:
                content_text = response.content.strip()
                follow_ups = generate_suggested_follow_ups(user_message, content_text)
                return {
                    "role": "assistant",
                    "content": content_text,
                    "sources": collected_sources,
                    "artifacts": generated_artifacts,
                    "follow_ups": follow_ups,
                    "provider": self.provider.provider_name,
                    "model": self.provider.model_name
                }

            for tool_call in response.tool_calls:
                tool_output = await self._execute_tool(tool_call, user_message, collected_sources, generated_artifacts, conversation_history)
                tool_results_history.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "name": tool_call.name,
                    "content": tool_output
                })

        final_content = response.content.strip() if response and response.content else ""
        if not final_content and collected_sources:
            synthesis_chunks = [
                f"**{s.get('guest')}** (*{s.get('episode_title')}*, Ep #{s.get('episode_number')}):\n> \"{s.get('excerpt')}\""
                for s in collected_sources[:3]
            ]
            final_content = "Based on Lenny's Podcast transcripts:\n\n" + "\n\n".join(synthesis_chunks)
        elif not final_content:
            final_content = "I could not find any discussion about this topic in Lenny's podcast transcript corpus."

        follow_ups = generate_suggested_follow_ups(user_message, final_content)
        return {
            "role": "assistant",
            "content": final_content,
            "sources": collected_sources,
            "artifacts": generated_artifacts,
            "follow_ups": follow_ups,
            "provider": self.provider.provider_name,
            "model": self.provider.model_name
        }

    async def execute_turn_stream(
        self,
        conversation_history: List[Dict[str, Any]],
        user_message: str,
        retrieve_filters: Optional[Dict[str, Any]] = None,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Streaming execution yielding real-time events, tool status, tokens, sources, and artifacts.

        When the selected provider is SDK-capable (ollama/anthropic) and the
        claude-agent-sdk package is installed, the turn runs through the
        official Claude Agent SDK (see sdk_adapter) with the same six tools
        exposed as in-process MCP tools. Any SDK failure falls back to the
        native loop below — before any event is emitted — so the product
        never breaks because of the SDK path.
        """
        if settings.AGENT_BACKEND == "claude-agent-sdk":
            from app.agents.sdk_adapter import AdapterError, execute_turn_stream_sdk
            try:
                async for event in execute_turn_stream_sdk(
                    conversation_history, user_message, retrieve_filters,
                    provider_type=self.provider_type,
                ):
                    yield event
                return
            except AdapterError as e:
                logger.warning("Agent SDK path unavailable (%s); using native loop.", e)

        messages = list(conversation_history)
        messages.append({"role": "user", "content": user_message})

        collected_sources: List[Dict[str, Any]] = []
        generated_artifacts: List[Dict[str, Any]] = []
        tool_results_history = list(messages)
        self._turn_filters = dict(retrieve_filters) if retrieve_filters else {}

        yield {"type": "status", "status": "Thinking & querying podcast transcripts..."}

        # Step 1: Tool check
        try:
            initial_resp: LLMResponse = await self.provider.generate(
                messages=tool_results_history,
                system_prompt=SYSTEM_PROMPT,
                tools=AVAILABLE_TOOLS
            )
        except Exception as e:
            yield {"type": "error", "message": f"Provider error ({self.provider.provider_name}): {str(e)}"}
            return

        if initial_resp.tool_calls:
            for tc in initial_resp.tool_calls:
                yield {"type": "tool_start", "tool": tc.name}
                tool_out = await self._execute_tool(tc, user_message, collected_sources, generated_artifacts, conversation_history)
                tool_results_history.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "name": tc.name,
                    "content": tool_out
                })
                yield {"type": "tool_end", "tool": tc.name, "sources_count": len(collected_sources)}

        if collected_sources:
            yield {"type": "sources", "sources": collected_sources}

        if generated_artifacts:
            yield {"type": "artifacts", "artifacts": generated_artifacts}

        # Step 2: Stream final text synthesis
        yield {"type": "status", "status": "Synthesizing grounded response..."}
        full_text = ""

        try:
            async for token in self.provider.generate_stream(
                messages=tool_results_history,
                system_prompt=SYSTEM_PROMPT,
                tools=None
            ):
                full_text += token
                yield {"type": "token", "token": token}
        except Exception as e:
            logger.error(f"Streaming token error: {e}", exc_info=True)
            if not full_text:
                full_text = "I have analyzed the transcripts and retrieved relevant insights."
                yield {"type": "token", "token": full_text}

        follow_ups = generate_suggested_follow_ups(user_message, full_text)
        yield {
            "type": "done",
            "full_content": full_text,
            "sources": collected_sources,
            "artifacts": generated_artifacts,
            "follow_ups": follow_ups,
            "provider": self.provider.provider_name,
            "model": self.provider.model_name
        }
