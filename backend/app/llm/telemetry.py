"""
Provider Telemetry & Resilience Layer.

- ProviderTelemetry: in-process, thread-safe per-provider counters
  (requests, errors, fallbacks, tool calls, latency, token estimates).
- InstrumentedProvider: transparent wrapper that records every generate /
  generate_stream call and performs one automatic model-discovery retry when
  a provider rejects the configured model (e.g. retired model -> HTTP 404).
"""
import time
import logging
import threading
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional, AsyncGenerator

from app.llm.provider import LLMProvider, LLMResponse

logger = logging.getLogger("lenny_growth.llm.telemetry")

# Substrings (lowercased) that indicate the configured model itself was
# rejected -- the trigger for auto-discovery fallback.
_MODEL_NOT_FOUND_MARKERS = [
    "does not exist",
    "model_not_found",
    "no longer available",
    "is not found",
    "not found: models/",
    "does not have access",
    "decommissioned",
]


def _looks_like_model_not_found(error: BaseException) -> bool:
    text = str(error).lower()
    return any(marker in text for marker in _MODEL_NOT_FOUND_MARKERS)


class ProviderTelemetry:
    """Thread-safe in-process telemetry store, keyed by provider name."""

    _EMPTY = {
        "requests_total": 0,
        "errors_total": 0,
        "fallbacks_total": 0,
        "tool_calls_total": 0,
        "latency_ms_total": 0.0,
        "latency_ms_max": 0.0,
        "tokens_in": 0,
        "tokens_out": 0,
        "last_error": None,
        "last_used_at": None,
    }

    def __init__(self):
        self._lock = threading.Lock()
        self._stats: Dict[str, Dict[str, Any]] = {}

    def _bucket(self, provider: str) -> Dict[str, Any]:
        if provider not in self._stats:
            self._stats[provider] = dict(self._EMPTY)
        return self._stats[provider]

    def record(
        self,
        provider: str,
        model: str,
        latency_ms: float,
        error: Optional[str] = None,
        fallback: bool = False,
        tool_calls: int = 0,
        tokens_in: int = 0,
        tokens_out: int = 0,
    ) -> None:
        with self._lock:
            b = self._bucket(provider)
            b["model"] = model
            b["requests_total"] += 1
            b["latency_ms_total"] += latency_ms
            b["latency_ms_max"] = max(b["latency_ms_max"], latency_ms)
            b["tool_calls_total"] += tool_calls
            b["tokens_in"] += tokens_in
            b["tokens_out"] += tokens_out
            b["last_used_at"] = datetime.now(timezone.utc).isoformat()
            if error is not None:
                b["errors_total"] += 1
                b["last_error"] = error[:300]
            if fallback:
                b["fallbacks_total"] += 1

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            providers = {}
            totals = {
                "requests_total": 0,
                "errors_total": 0,
                "fallbacks_total": 0,
                "tool_calls_total": 0,
            }
            for name, b in self._stats.items():
                entry = dict(b)
                entry["avg_latency_ms"] = (
                    round(b["latency_ms_total"] / b["requests_total"], 1)
                    if b["requests_total"] else 0.0
                )
                entry["latency_ms_total"] = round(b["latency_ms_total"], 1)
                entry["latency_ms_max"] = round(b["latency_ms_max"], 1)
                providers[name] = entry
                for key in totals:
                    totals[key] += b[key]
            return {"providers": providers, "totals": totals}

    def reset(self) -> None:
        with self._lock:
            self._stats.clear()


telemetry = ProviderTelemetry()


def extract_token_usage(usage: Dict[str, Any]) -> (int, int):
    """Normalize token counts across OpenAI-style, Groq, and Ollama usage shapes."""
    if not isinstance(usage, dict):
        return 0, 0
    tokens_in = (
        usage.get("prompt_tokens")
        or usage.get("prompt_eval_count")
        or 0
    )
    tokens_out = (
        usage.get("completion_tokens")
        or usage.get("eval_count")
        or 0
    )
    try:
        return int(tokens_in), int(tokens_out)
    except (TypeError, ValueError):
        return 0, 0


# Preference ranking for auto-discovered replacement models: strong
# general-purpose chat families first, unknown/exotic families last.
_MODEL_PREFERENCE = ("gpt-oss", "llama", "qwen", "gemini", "deepseek", "groq/compound")


def _rank_candidates(candidates: List[str]) -> List[str]:
    def score(name: str) -> int:
        lowered = name.lower()
        for i, pref in enumerate(_MODEL_PREFERENCE):
            if pref in lowered:
                return i
        return len(_MODEL_PREFERENCE)

    return sorted(candidates, key=score)


class InstrumentedProvider(LLMProvider):
    """Wraps any LLMProvider: records telemetry and auto-heals dead model refs."""

    def __init__(self, inner: LLMProvider):
        self._inner = inner

    @property
    def provider_name(self) -> str:
        return self._inner.provider_name

    @property
    def model_name(self) -> str:
        return self._inner.model_name

    async def check_health(self) -> Dict[str, Any]:
        return await self._inner.check_health()

    async def discover_models(self) -> List[str]:
        finder = getattr(self._inner, "discover_models", None)
        if finder is None:
            return []
        try:
            return await finder()
        except Exception as e:
            logger.warning(f"Model discovery failed for {self.provider_name}: {e}")
            return []

    async def _retry_with_discovered_model(
        self,
        original_error: Exception,
        messages, system_prompt, tools, kwargs
    ) -> LLMResponse:
        candidates = [
            m for m in _rank_candidates([
                m for m in await self.discover_models()
                if m and m != self._inner.model
            ])
        ]
        if not candidates:
            raise original_error

        new_model = candidates[0]
        logger.warning(
            f"{self.provider_name}: model '{self._inner.model}' unavailable; "
            f"falling back to '{new_model}'"
        )
        self._inner.model = new_model

        resp = await self._inner.generate(
            messages, system_prompt, tools, **kwargs
        )
        telemetry.record(
            provider=self.provider_name,
            model=new_model,
            latency_ms=0.0,  # already accounted on the outer call
            fallback=True,
        )
        return resp

    async def generate(
        self,
        messages: List[Dict[str, Any]],
        system_prompt: str,
        tools: Optional[List[Dict[str, Any]]] = None,
        **kwargs
    ) -> LLMResponse:
        start = time.perf_counter()
        try:
            resp = await self._inner.generate(messages, system_prompt, tools, **kwargs)
        except Exception as e:
            latency = (time.perf_counter() - start) * 1000
            if _looks_like_model_not_found(e):
                try:
                    return await self._retry_with_discovered_model(
                        e, messages, system_prompt, tools, kwargs
                    )
                except Exception as retry_err:
                    telemetry.record(
                        provider=self.provider_name,
                        model=self._inner.model,
                        latency_ms=latency,
                        error=str(retry_err),
                        fallback=True,
                    )
                    raise
            telemetry.record(
                provider=self.provider_name,
                model=self._inner.model,
                latency_ms=latency,
                error=str(e),
            )
            raise

        latency = (time.perf_counter() - start) * 1000
        tokens_in, tokens_out = extract_token_usage(resp.token_usage)
        telemetry.record(
            provider=self.provider_name,
            model=resp.model,
            latency_ms=latency,
            tool_calls=len(resp.tool_calls),
            tokens_in=tokens_in,
            tokens_out=tokens_out,
        )
        return resp

    async def generate_stream(
        self,
        messages: List[Dict[str, Any]],
        system_prompt: str,
        tools: Optional[List[Dict[str, Any]]] = None,
        **kwargs
    ) -> AsyncGenerator[str, None]:
        start = time.perf_counter()
        chars = 0
        try:
            async for token in self._inner.generate_stream(messages, system_prompt, tools, **kwargs):
                chars += len(token)
                yield token
        except Exception as e:
            latency = (time.perf_counter() - start) * 1000
            telemetry.record(
                provider=self.provider_name,
                model=self._inner.model,
                latency_ms=latency,
                error=str(e),
            )
            raise
        latency = (time.perf_counter() - start) * 1000
        telemetry.record(
            provider=self.provider_name,
            model=self._inner.model,
            latency_ms=latency,
            tokens_out=max(1, chars // 4),  # ~4 chars per token estimate
        )

    def __getattr__(self, name: str) -> Any:
        if name == "_inner":
            raise AttributeError(name)
        return getattr(self._inner, name)

