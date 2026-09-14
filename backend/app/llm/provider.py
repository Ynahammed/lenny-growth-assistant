"""
LLM Provider Abstraction Layer for Lenny Growth Assistant.
Supports:
- Ollama (Local llama3.2 / mistral)
- Groq (Cloud GPT-OSS 120B - ultra fast)
- Gemini (Google AI Gemini 3.6)
- Mock (Zero-setup local testing / fallback)
"""
import os
import json
import logging
import asyncio
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional, AsyncGenerator
from pydantic import BaseModel
import httpx
from app.config import settings

logger = logging.getLogger("lenny_growth.llm")


class ToolCall(BaseModel):
    id: str
    name: str
    arguments: Dict[str, Any]


class LLMResponse(BaseModel):
    content: str = ""
    tool_calls: List[ToolCall] = []
    provider: str
    model: str
    token_usage: Dict[str, Any] = {}
    raw: Optional[Dict[str, Any]] = None


class LLMProvider(ABC):
    """Abstract base class for all LLM providers."""

    @property
    @abstractmethod
    def provider_name(self) -> str:
        pass

    @property
    @abstractmethod
    def model_name(self) -> str:
        pass

    @abstractmethod
    async def check_health(self) -> Dict[str, Any]:
        pass

    @abstractmethod
    async def generate(
        self,
        messages: List[Dict[str, Any]],
        system_prompt: str,
        tools: Optional[List[Dict[str, Any]]] = None,
        **kwargs
    ) -> LLMResponse:
        pass

    async def generate_stream(
        self,
        messages: List[Dict[str, Any]],
        system_prompt: str,
        tools: Optional[List[Dict[str, Any]]] = None,
        **kwargs
    ) -> AsyncGenerator[str, None]:
        """Default streaming fallback: calls generate and yields content chunks."""
        resp = await self.generate(messages, system_prompt, tools, **kwargs)
        if resp.content:
            # Chunk words for a natural smooth typing cadence
            words = resp.content.split(" ")
            for i, word in enumerate(words):
                yield word + (" " if i < len(words) - 1 else "")
                await asyncio.sleep(0.01)


# =====================================================================
# 1. Ollama Provider (Local)
# =====================================================================
class OllamaProvider(LLMProvider):
    """Ollama Local Model Provider."""

    def __init__(self, base_url: str = None, model: str = None):
        self.base_url = (base_url or settings.OLLAMA_BASE_URL).rstrip("/")
        self.model = model or settings.OLLAMA_MODEL

    @property
    def provider_name(self) -> str:
        return "ollama"

    @property
    def model_name(self) -> str:
        return self.model

    async def discover_models(self) -> List[str]:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                res = await client.get(f"{self.base_url}/api/tags")
            if res.status_code != 200:
                return []
            return [m.get("name") for m in res.json().get("models", []) if m.get("name")]
        except Exception:
            return []

    async def check_health(self) -> Dict[str, Any]:
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                res = await client.get(f"{self.base_url}/api/tags")
                if res.status_code == 200:
                    models = [m.get("name") for m in res.json().get("models", [])]
                    return {
                        "status": "healthy",
                        "provider": "ollama",
                        "model": self.model,
                        "available_models": models
                    }
                return {"status": "unhealthy", "error": f"Ollama HTTP {res.status_code}"}
        except Exception as e:
            return {"status": "unreachable", "error": f"Cannot connect to Ollama at {self.base_url}: {e}"}

    def _prepare_payload(self, messages: List[Dict[str, Any]], system_prompt: str, tools: Optional[List[Dict[str, Any]]], stream: bool = False, **kwargs) -> Dict[str, Any]:
        ollama_messages = [{"role": "system", "content": system_prompt}]
        for msg in messages:
            role = msg.get("role", "user")
            content = str(msg.get("content", ""))
            if role == "tool":
                ollama_messages.append({
                    "role": "user",
                    "content": f"[Retrieved Podcast Transcripts Evidence]:\n{content}\n\nPlease synthesize a clear, comprehensive answer grounded in these transcript excerpts. Cite the guest and episode."
                })
            else:
                ollama_messages.append({"role": role, "content": content})

        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": ollama_messages,
            "stream": stream,
            "options": {
                "temperature": kwargs.get("temperature", 0.3),
            }
        }

        if tools:
            ollama_tools = []
            for t in tools:
                if "function" in t:
                    ollama_tools.append(t)
                else:
                    ollama_tools.append({
                        "type": "function",
                        "function": {
                            "name": t.get("name", "retrieve"),
                            "description": t.get("description", ""),
                            "parameters": t.get("parameters", {"type": "object", "properties": {}})
                        }
                    })
            payload["tools"] = ollama_tools

        return payload

    async def generate(
        self,
        messages: List[Dict[str, Any]],
        system_prompt: str,
        tools: Optional[List[Dict[str, Any]]] = None,
        **kwargs
    ) -> LLMResponse:
        payload = self._prepare_payload(messages, system_prompt, tools, stream=False, **kwargs)

        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(300.0, connect=10.0)) as client:
                res = await client.post(f"{self.base_url}/api/chat", json=payload)
                if res.status_code != 200:
                    raise RuntimeError(f"Ollama error ({res.status_code}): {res.text}")
                data = res.json()
        except httpx.ConnectError:
            raise ConnectionError(
                f"Could not connect to Ollama server at {self.base_url}. Ensure Ollama is running (`ollama serve`) or switch to another provider."
            )
        except httpx.ReadTimeout:
            raise ConnectionError(
                f"Ollama timed out generating a response. Please try again in a moment."
            )

        msg_obj = data.get("message", {})
        content_text = msg_obj.get("content", "")
        tool_calls: List[ToolCall] = []

        if "tool_calls" in msg_obj and msg_obj["tool_calls"]:
            for idx, tc in enumerate(msg_obj["tool_calls"]):
                func = tc.get("function", {})
                name = func.get("name") or tc.get("name") or ""
                args = func.get("arguments", {})
                if isinstance(args, str):
                    try:
                        args = json.loads(args)
                    except Exception:
                        args = {}
                
                if not name:
                    if "type" in args and args["type"] in ["retrieve", "ship30_essay", "artifact_gen", "prd_generator", "pre_mortem_simulator", "growth_audit"]:
                        name = args["type"]
                    elif "query" in args or "q" in args:
                        name = "retrieve"
                    elif "problem_statement" in args:
                        name = "prd_generator"
                    elif "initiative_name" in args:
                        name = "pre_mortem_simulator"
                    elif "business_model" in args:
                        name = "growth_audit"
                    else:
                        name = "retrieve"

                tool_calls.append(ToolCall(id=f"call_{idx}", name=name, arguments=args))

        return LLMResponse(
            content=content_text,
            tool_calls=tool_calls,
            provider="ollama",
            model=self.model,
            token_usage={
                "prompt_eval_count": data.get("prompt_eval_count", 0),
                "eval_count": data.get("eval_count", 0)
            },
            raw=data
        )

    async def generate_stream(
        self,
        messages: List[Dict[str, Any]],
        system_prompt: str,
        tools: Optional[List[Dict[str, Any]]] = None,
        **kwargs
    ) -> AsyncGenerator[str, None]:
        payload = self._prepare_payload(messages, system_prompt, tools=None, stream=True, **kwargs)

        async with httpx.AsyncClient(timeout=httpx.Timeout(300.0, connect=10.0)) as client:
            async with client.stream("POST", f"{self.base_url}/api/chat", json=payload) as response:
                if response.status_code != 200:
                    err_text = await response.aread()
                    raise RuntimeError(f"Ollama streaming error ({response.status_code}): {err_text.decode('utf-8')}")
                
                async for line in response.aiter_lines():
                    if not line:
                        continue
                    try:
                        chunk_json = json.loads(line)
                        chunk_content = chunk_json.get("message", {}).get("content", "")
                        if chunk_content:
                            yield chunk_content
                    except Exception:
                        continue


# =====================================================================
# 2. Groq Provider (Ultra-Fast Cloud Llama 3.3 70B)
# =====================================================================
class GroqProvider(LLMProvider):
    """Groq Cloud Provider delivering 500+ tokens/sec."""

    def __init__(self, api_key: str = None, model: str = None):
        self.api_key = api_key or settings.GROQ_API_KEY
        self.model = model or settings.GROQ_MODEL
        self.base_url = "https://api.groq.com/openai/v1"

    @property
    def provider_name(self) -> str:
        return "groq"

    @property
    def model_name(self) -> str:
        return self.model

    async def discover_models(self) -> List[str]:
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.get(
                    f"{self.base_url}/models",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                )
            if res.status_code != 200:
                return []
            excluded = ("whisper", "tts", "guard", "embed", "safeguard")
            ids = [m.get("id") for m in res.json().get("data", []) if m.get("id")]
            return [
                i for i in ids
                if not any(x in i.lower() for x in excluded)
            ]
        except Exception:
            return []

    async def check_health(self) -> Dict[str, Any]:
        if not self.api_key:
            return {"status": "unconfigured", "error": "GROQ_API_KEY is not set. Get a free key at https://console.groq.com"}
        try:
            headers = {"Authorization": f"Bearer {self.api_key}"}
            async with httpx.AsyncClient(timeout=5.0) as client:
                res = await client.get(f"{self.base_url}/models", headers=headers)
                if res.status_code == 200:
                    return {"status": "healthy", "provider": "groq", "model": self.model}
                return {"status": "unhealthy", "error": f"Groq HTTP {res.status_code}: {res.text}"}
        except Exception as e:
            return {"status": "unreachable", "error": f"Cannot connect to Groq: {e}"}

    def _format_messages(self, messages: List[Dict[str, Any]], system_prompt: str) -> List[Dict[str, Any]]:
        formatted = [{"role": "system", "content": system_prompt}]
        for m in messages:
            role = m.get("role", "user")
            content = str(m.get("content", ""))
            if role == "tool":
                formatted.append({
                    "role": "user",
                    "content": f"[Retrieved Podcast Transcripts]:\n{content}\n\nPlease synthesize a response based on this transcript evidence. Cite the guest and episode."
                })
            else:
                formatted.append({"role": role, "content": content})
        return formatted

    async def generate(
        self,
        messages: List[Dict[str, Any]],
        system_prompt: str,
        tools: Optional[List[Dict[str, Any]]] = None,
        **kwargs
    ) -> LLMResponse:
        if not self.api_key:
            raise ValueError("GROQ_API_KEY is not set. Set GROQ_API_KEY in backend/.env or switch to Ollama/Mock.")

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": self._format_messages(messages, system_prompt),
            "temperature": kwargs.get("temperature", 0.3),
            "max_tokens": kwargs.get("max_tokens", 2048)
        }

        if tools:
            groq_tools = []
            for t in tools:
                groq_tools.append({
                    "type": "function",
                    "function": {
                        "name": t.get("name", "retrieve"),
                        "description": t.get("description", ""),
                        "parameters": t.get("parameters", {"type": "object", "properties": {}})
                    }
                })
            payload["tools"] = groq_tools

        async with httpx.AsyncClient(timeout=30.0) as client:
            res = await client.post(f"{self.base_url}/chat/completions", headers=headers, json=payload)
            if res.status_code != 200:
                raise RuntimeError(f"Groq API Error ({res.status_code}): {res.text}")
            data = res.json()

        choice = data.get("choices", [{}])[0]
        msg = choice.get("message", {})
        content = msg.get("content", "") or ""
        tool_calls: List[ToolCall] = []

        if "tool_calls" in msg and msg["tool_calls"]:
            for idx, tc in enumerate(msg["tool_calls"]):
                func = tc.get("function", {})
                args = func.get("arguments", {})
                if isinstance(args, str):
                    try:
                        args = json.loads(args)
                    except Exception:
                        args = {}
                tool_calls.append(ToolCall(
                    id=tc.get("id", f"call_groq_{idx}"),
                    name=func.get("name", "retrieve"),
                    arguments=args
                ))

        return LLMResponse(
            content=content,
            tool_calls=tool_calls,
            provider="groq",
            model=self.model,
            token_usage=data.get("usage", {}),
            raw=data
        )

    async def generate_stream(
        self,
        messages: List[Dict[str, Any]],
        system_prompt: str,
        tools: Optional[List[Dict[str, Any]]] = None,
        **kwargs
    ) -> AsyncGenerator[str, None]:
        if not self.api_key:
            raise ValueError("GROQ_API_KEY is not set.")

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": self._format_messages(messages, system_prompt),
            "temperature": kwargs.get("temperature", 0.3),
            "max_tokens": kwargs.get("max_tokens", 2048),
            "stream": True
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            async with client.stream("POST", f"{self.base_url}/chat/completions", headers=headers, json=payload) as response:
                if response.status_code != 200:
                    err_text = await response.aread()
                    raise RuntimeError(f"Groq stream error ({response.status_code}): {err_text.decode('utf-8')}")
                
                async for line in response.aiter_lines():
                    if not line or not line.startswith("data: "):
                        continue
                    data_str = line[6:].strip()
                    if data_str == "[DONE]":
                        break
                    try:
                        chunk_json = json.loads(data_str)
                        delta = chunk_json.get("choices", [{}])[0].get("delta", {})
                        chunk_content = delta.get("content", "")
                        if chunk_content:
                            yield chunk_content
                    except Exception:
                        continue


# =====================================================================
# 3. Google Gemini Provider
# =====================================================================
class GeminiProvider(LLMProvider):
    """Google Gemini Provider using Gemini REST API."""

    def __init__(self, api_key: str = None, model: str = None):
        self.api_key = api_key or settings.GEMINI_API_KEY
        self.model = model or settings.GEMINI_MODEL    @property
    def provider_name(self) -> str:
        return "gemini"

    @property
    def model_name(self) -> str:
        return self.model

    async def discover_models(self) -> List[str]:
        try:
            url = (
                "https://generativelanguage.googleapis.com/v1beta/models"
                f"?key={self.api_key}&pageSize=200"
            )
            async with httpx.AsyncClient(timeout=15.0) as client:
                res = await client.get(url)
            if res.status_code != 200:
                return []
            names = []
            for m in res.json().get("models", []):
                methods = m.get("supportedGenerationMethods", [])
                name = (m.get("name") or "").removeprefix("models/")
                if name and "generateContent" in methods:
                    names.append(name)
            return names
        except Exception:
            return []

    async def check_health(self) -> Dict[str, Any]:
        if not self.api_key:
            return {"status": "unconfigured", "error": "GEMINI_API_KEY is not set. Get a free key at https://aistudio.google.com"}
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}?key={self.api_key}"
            async with httpx.AsyncClient(timeout=5.0) as client:
                res = await client.get(url)
                if res.status_code == 200:
                    return {"status": "healthy", "provider": "gemini", "model": self.model}
                return {"status": "unhealthy", "error": f"Gemini HTTP {res.status_code}: {res.text}"}
        except Exception as e:
            return {"status": "unreachable", "error": f"Cannot connect to Gemini: {e}"}

    @staticmethod
    def _clean_schema(schema: Any) -> Any:
        """Strip JSON-Schema keywords Gemini's function declaration API rejects."""
        if not isinstance(schema, dict):
            return schema
        allowed = {"type", "description", "enum", "items", "properties", "required", "format"}
        cleaned: Dict[str, Any] = {}
        for key, value in schema.items():
            if key not in allowed:
                continue
            if key == "properties" and isinstance(value, dict):
                cleaned[key] = {pk: GeminiProvider._clean_schema(pv) for pk, pv in value.items()}
            elif key == "items" and isinstance(value, dict):
                cleaned[key] = GeminiProvider._clean_schema(value)
            else:
                cleaned[key] = value
        return cleaned

    def _build_payload(
        self,
        messages: List[Dict[str, Any]],
        system_prompt: str,
        tools: Optional[List[Dict[str, Any]]] = None,
        **kwargs
    ) -> Dict[str, Any]:
        contents = []
        for m in messages:
            role = "user" if m.get("role") in ["user", "tool"] else "model"
            content = str(m.get("content", ""))
            if m.get("role") == "tool":
                content = f"[Retrieved Podcast Transcripts]:\n{content}\n\nPlease synthesize a response citing the guest and episode."
            contents.append({"role": role, "parts": [{"text": content}]})

        payload: Dict[str, Any] = {
            "system_instruction": {"parts": [{"text": system_prompt}]},
            "contents": contents,
            "generationConfig": {
                "temperature": kwargs.get("temperature", 0.3),
                "maxOutputTokens": kwargs.get("max_tokens", 8192)
            }
        }

        if tools:
            payload["tools"] = [{
                "function_declarations": [
                    {
                        "name": t.get("name", "retrieve"),
                        "description": t.get("description", ""),
                        "parameters": self._clean_schema(t.get("parameters", {"type": "object", "properties": {}}))
                    }
                    for t in tools
                ]
            }]

        return payload

    @staticmethod
    def _extract_parts(data: Dict[str, Any]):
        candidates = data.get("candidates", [])
        if not candidates:
            return [], ""
        return candidates[0].get("content", {}).get("parts", []), candidates[0].get("finishReason", "")

    async def generate(
        self,
        messages: List[Dict[str, Any]],
        system_prompt: str,
        tools: Optional[List[Dict[str, Any]]] = None,
        **kwargs
    ) -> LLMResponse:
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY is not set. Set GEMINI_API_KEY in backend/.env or switch to Ollama/Mock.")

        payload = self._build_payload(messages, system_prompt, tools, **kwargs)
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent?key={self.api_key}"

        async with httpx.AsyncClient(timeout=60.0) as client:
            res = await client.post(url, json=payload)
            if res.status_code != 200:
                raise RuntimeError(f"Gemini API error ({res.status_code}): {res.text}")
            data = res.json()

        parts, _finish = self._extract_parts(data)
        text = "".join(p.get("text", "") for p in parts if not p.get("thought"))

        tool_calls: List[ToolCall] = []
        for idx, p in enumerate(parts):
            fc = p.get("functionCall")
            if fc:
                args = fc.get("args", {}) or {}
                if isinstance(args, str):
                    try:
                        args = json.loads(args)
                    except Exception:
                        args = {}
                tool_calls.append(ToolCall(
                    id=f"call_gemini_{idx}",
                    name=fc.get("name", "retrieve"),
                    arguments=args
                ))

        return LLMResponse(
            content=text,
            tool_calls=tool_calls,
            provider="gemini",
            model=self.model,
            raw=data
        )

    async def generate_stream(
        self,
        messages: List[Dict[str, Any]],
        system_prompt: str,
        tools: Optional[List[Dict[str, Any]]] = None,
        **kwargs
    ) -> AsyncGenerator[str, None]:
        """Real SSE streaming via streamGenerateContent (tools unsupported while streaming)."""
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY is not set.")

        payload = self._build_payload(messages, system_prompt, tools=None, **kwargs)
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:streamGenerateContent?alt=sse&key={self.api_key}"

        async with httpx.AsyncClient(timeout=120.0) as client:
            async with client.stream("POST", url, json=payload) as response:
                if response.status_code != 200:
                    err_text = await response.aread()
                    raise RuntimeError(f"Gemini stream error ({response.status_code}): {err_text.decode('utf-8')}")

                async for line in response.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    try:
                        chunk = json.loads(line[6:])
                    except Exception:
                        continue
                    parts, _finish = self._extract_parts(chunk)
                    for p in parts:
                        token = p.get("text", "")
                        if token and not p.get("thought"):
                            yield token


# =====================================================================
# 4. Mock Provider (Zero-Setup & CI/CD)
# =====================================================================
class MockProvider(LLMProvider):
    """Deterministic Mock Provider for testing and instant zero-setup answers."""

    def __init__(self, model: str = "mock-pm-engine"):
        self.model = model

    @property
    def provider_name(self) -> str:
        return "mock"

    @property
    def model_name(self) -> str:
        return self.model

    async def check_health(self) -> Dict[str, Any]:
        return {"status": "healthy", "provider": "mock", "model": self.model}

    async def generate(
        self,
        messages: List[Dict[str, Any]],
        system_prompt: str,
        tools: Optional[List[Dict[str, Any]]] = None,
        **kwargs
    ) -> LLMResponse:
        last_msg = messages[-1] if messages else {"content": ""}
        content_str = str(last_msg.get("content", "")).lower()
        has_tool_results = any(m.get("role") == "tool" for m in messages)
        
        # Step 1: Tool dispatch on first iteration
        if tools and not has_tool_results:
            if "prd" in content_str:
                return LLMResponse(
                    content="",
                    tool_calls=[ToolCall(
                        id="call_mock_prd",
                        name="prd_generator",
                        arguments={"title": "Automated Retention Loop", "problem_statement": "Users drop off before experiencing core time-to-value"}
                    )],
                    provider="mock",
                    model=self.model
                )
            elif "pre-mortem" in content_str or "pre mortem" in content_str or "premortem" in content_str:
                return LLMResponse(
                    content="",
                    tool_calls=[ToolCall(
                        id="call_mock_premortem",
                        name="pre_mortem_simulator",
                        arguments={"initiative_name": "New B2B Self-Serve Onboarding", "launch_context": "Transitioning from sales-assisted to self-serve PLG"}
                    )],
                    provider="mock",
                    model=self.model
                )
            elif "audit" in content_str or "funnel" in content_str:
                return LLMResponse(
                    content="",
                    tool_calls=[ToolCall(
                        id="call_mock_audit",
                        name="growth_audit",
                        arguments={"business_model": "B2B SaaS / PLG", "funnel_metrics": "10k Visitors -> 500 Signups -> 50 Activated -> 10 Paid"}
                    )],
                    provider="mock",
                    model=self.model
                )
            elif any(t["name"] == "retrieve" for t in tools):
                return LLMResponse(
                    content="",
                    tool_calls=[ToolCall(
                        id="call_mock_retrieve",
                        name="retrieve",
                        arguments={"query": last_msg.get("content", ""), "top_k": 4}
                    )],
                    provider="mock",
                    model=self.model
                )

        # Step 2: Grounded Synthesis
        user_queries = [str(m.get("content", "")).lower() for m in messages if m.get("role") == "user"]
        user_text = " ".join(user_queries)

        if any(kw in user_text for kw in ["sourdough", "bread", "mars", "weather", "recipe", "cake"]):
            return LLMResponse(
                content="I could not find any discussion of this topic in Lenny's podcast transcript corpus. I answer strictly from verified podcast episodes to prevent hallucinations.",
                provider="mock",
                model=self.model
            )

        if "rahul" in user_text or "pmf" in user_text or "superhuman" in user_text:
            answer = (
                "According to **Rahul Vohra** (*How Superhuman Built an Engine to Find Product-Market Fit*, Ep #64), "
                "PMF can be reverse-engineered using the Sean Ellis survey question: *'How would you feel if you could no longer use the product?'*\n\n"
                "Key principles:\n"
                "- **The 40% Benchmark:** If >=40% of users answer 'very disappointed', you have product-market fit.\n"
                "- **Segment High-Expectation Customers (HXC):** Focus relentlessly on the users who love your product most (e.g. founders, heavy triage users) and ignore detractors who are outside your ICP.\n"
                "- **The 100ms Rule:** Actions completing under 100ms induce psychological flow and feel instantaneous."
            )
            return LLMResponse(content=answer, provider="mock", model=self.model)

        if "gustaf" in user_text or "retention curve" in user_text or "yc" in user_text:
            answer = (
                "According to **Gustaf Alströmer** (*The YC Growth Playbook & Retention Curves*, Ep #52), "
                "the #1 mistake early founders make is pouring acquisition spend into a **leaky bucket**.\n\n"
                "1. **Cohort Asymptote:** A healthy retention curve flattens parallel to the x-axis. If it slopes toward zero, stop marketing and fix activation.\n"
                "2. **True North Star Metric:** Captures the moment of real customer value (e.g. nights booked for Airbnb, rides completed for Uber) rather than lagging revenue."
            )
            return LLMResponse(content=answer, provider="mock", model=self.model)

        if "moesta" in user_text or "jtbd" in user_text or "jobs to be done" in user_text:
            answer = (
                "According to **Bob Moesta** (*Unpacking Jobs-to-be-Done & The 4 Forces of Progress*, Ep #91), "
                "customers don't buy products—they 'hire' them to make progress during a struggling moment.\n\n"
                "**The Four Forces of Progress:**\n"
                "- **Push of Present:** Acute frustration with current tool.\n"
                "- **Pull of New:** Magnetic promise of the new solution.\n"
                "- **Anxiety of New:** Fear of migration and unknown failure.\n"
                "- **Habit of Present:** Inertia and comfort of existing routine.\n\n"
                "*Key Takeaway:* Most PMs over-index on increasing Pull, but reducing Anxiety yields 10x more conversions."
            )
            return LLMResponse(content=answer, provider="mock", model=self.model)

        if "shreyas" in user_text or "lno" in user_text or "priorit" in user_text:
            answer = (
                "According to **Shreyas Doshi** (*High-Agency Product Management, The LNO Framework*, Ep #78), PM burnout happens "
                "when managers apply 100% perfectionist effort across every task. The LNO framework categorizes work into:\n\n"
                "1. **Leverage Tasks (10x ROI):** Strategy, high-stakes PRDs, and key hires. Deliberately over-invest time here for 100% excellence.\n"
                "2. **Neutral Tasks (1x ROI):** Sprint planning, routine updates. 80% quality is sufficient; extra effort yields zero marginal return.\n"
                "3. **Overhead Tasks (<0.1x ROI):** Administrative forms and minor meetings. Complete at minimum acceptable threshold or automate/eliminate."
            )
            return LLMResponse(content=answer, provider="mock", model=self.model)

        if "casey" in user_text or "activation" in user_text or "marketplace" in user_text:
            answer = (
                "Based on **Casey Winters** (*Growth Loops, Activation Metrics, and Marketplace Dynamics*, Ep #42), "
                "activation in a marketplace is **not** account creation—that is a vanity metric.\n\n"
                "Key takeaways:\n"
                "- **Demand-side Activation:** Defined as the user's first completed transaction/booking within a critical 7-to-14 day window.\n"
                "- **Supply-side Activation:** Measured as *Time to First Dollar Earned*.\n"
                "- **Growth Loops vs. Funnels:** Closed loops turn active users into creators of indexable pages or invites for the next cohort."
            )
            return LLMResponse(content=answer, provider="mock", model=self.model)

        return LLMResponse(
            content="Based on Lenny's Podcast transcripts, high-performing product and growth teams focus on deep customer activation, high-leverage prioritization (LNO), and closed growth loops.",
            provider="mock",
            model=self.model
        )


def get_provider(provider_type: Optional[str] = None, instrument: bool = True) -> LLMProvider:
    """Factory function returning the configured LLMProvider.

    Wrapped in InstrumentedProvider by default: records call telemetry and
    auto-recovers when the configured model has been retired (HTTP 404).
    """
    choice = (provider_type or settings.LLM_PROVIDER).strip().lower()

    if choice == "groq":
        if not settings.GROQ_API_KEY:
            logger.warning("Groq API key missing. Falling back to Ollama or Mock.")
            inner: LLMProvider = OllamaProvider()
        else:
            inner = GroqProvider()
    elif choice == "gemini":
        if not settings.GEMINI_API_KEY:
            logger.warning("Gemini API key missing. Falling back to Ollama or Mock.")
            inner = OllamaProvider()
        else:
            inner = GeminiProvider()
    elif choice == "mock":
        inner = MockProvider()
    else:
        if choice != "ollama":
            logger.info(f"Using default Ollama provider for choice '{choice}'.")
        inner = OllamaProvider()

    if not instrument:
        return inner
    from app.llm.telemetry import InstrumentedProvider
    return InstrumentedProvider(inner)
