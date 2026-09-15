# PRD — The Lenny Growth Assistant

*Forward-deployed engagement: turn Lenny's Podcast transcripts into a reliable internal assistant for a product & growth team.*

---

## 1. Discovery brief

### User and problem

**Primary user:** a product manager or growth lead at a consumer/subscription business who consumes Lenny's Podcast but cannot retrieve its tactical advice at the moment of decision. Their real job-to-be-done: *"I'm deciding on X this week — what did the best operators say about X, and can I turn it into something I can share with my team today?"*

**Pain removed (before → after):**

| Before | After |
|---|---|
| Advice is locked inside 2–3 hour episodes; recall depends on memory | Answers in seconds, each grounded in cited transcript excerpts (guest, episode, quote) |
| Reusing advice means re-typing it into docs and essays | One click turns a grounded answer into a PRD, pre-mortem, growth audit, styled artifact, or a ~1,250-word publishable essay |
| Off-topic questions get confident-sounding guesses from a generic chatbot | The system refuses when transcript evidence is below a calibrated relevance threshold — trust is the product |

### Success metric

**Primary product metric:** ≥ 85% of answered turns include at least one transcript citation, and the offline groundedness eval suite (33 known Q&A cases, `pytest -m eval`) maintains ≥ 90% pass rate on retrieval relevance, refusal correctness, and citation accuracy. CI runs this nightly so retrieval regressions are caught automatically.

**Operational metrics (from `/api/health` + structured logs):** provider availability and per-request latency visible without a debugger; a failed provider/model visibly degrades (auto-fallback) rather than silently changing answers.

### Assumptions

1. **Single-tenant internal tool.** One team; no per-user auth in v1 (documented as a scope cut, not an oversight).
2. **Corpus is fixed and small** (~48 transcript chunks across episodes in the repo's `data/` corpus). Refresh is a re-run of the ingestion script, not a live pipeline.
3. **Users bring their own model keys** (Groq / Gemini / Anthropic) or run Ollama locally. Keys never leave `.env`; the server never proxies them anywhere but the provider.
4. **"Grounded" means transcript-evidenced.** General knowledge answers, even if correct, are treated as failures when evidence falls below threshold.
5. **Evaluators run this locally** (Docker Compose or native Python), so one-command startup and a mock provider (zero keys needed for tests) are first-class.

### Scope

**Included:** grounded RAG chat with streaming, follow-up context (query contextualization), refusal gate, metadata filtering (guest/episode chips), five generation skills (PRD, pre-mortem, growth audit, Ship 30 essay, styled HTML/markdown artifact), sandboxed in-app artifact viewer, session management (rename/undo-delete/bulk clear), two themes, provider switching per message with auto-fallback, eval suite, CI.

**Intentionally excluded (and why):**
- **Auth/multi-tenancy** — the engagement is one internal team; auth would add setup friction for evaluators without product value in this setting.
- **Live transcript ingestion** — the corpus is a curated snapshot; automating scraping adds fragility, not learning value.
- **Anthropic/Pi SDK for every provider** — the Claude Agent SDK path is implemented (default backend) but routes only through Anthropic-Messages-compatible endpoints (Ollama/Anthropic); Groq/Gemini use the native loop by necessity (see architecture.md §Agent backends).
- **Vector DB beyond ChromaDB** — at 48 chunks, pgvector/Qdrant is over-engineering; the boundary is documented for future scale.

### Risks and trade-offs

| Risk | Mitigation |
|---|---|
| **Hallucination** | Two-stage retrieval (bge bi-encoder → cross-encoder rerank) + cosine gate (0.62) + LLM refusal instruction + refusal-correctness evals |
| **Latency** | Streaming SSE from first token; tool/status events keep perceived latency low; Groq for speed; local Ollama works offline |
| **Local model quality** | Small models (≤3B) often skip tool calls — documented; recommendation to use ≥7B (e.g. qwen2.5:7b-instruct) for the SDK path; native loop is the fallback |
| **Cost** | Default provider is local (Ollama); cloud keys optional; rewrite/essay calls are bounded (one expansion round max) |
| **Data leakage** | Keys only in `.env` (gitignored); `.env.example` carries safe defaults; logs redact secrets |
| **Unsafe artifact rendering** | Generated HTML treated as untrusted: allowlist sanitization server-side (nh3) + sandboxed iframe client-side (no scripts, no app-origin access). Full rationale in design.md §Security |

---

## 2. Product flows

### Flow A — Grounded question (core loop)
1. User types a question (optionally with guest/episode filter chips active).
2. Agent decides to call `retrieve`; vague follow-ups are first rewritten with conversation context ("what about retention?" → "how do I improve user retention for a B2B SaaS after PMF?").
3. Retrieval runs: bi-encoder candidates → cross-encoder rerank → cosine gate. Chunks above threshold become **sources** (rendered as citation pills with guest/episode).
4. Below threshold → the agent **refuses** and says what the corpus *does* cover.
5. Answer streams token-by-token; sources and any artifacts render inline; the turn is persisted (session, message, artifacts).

### Flow B — Content creation
1. User asks for "a PRD for X" / "an essay on Y" mid-conversation.
2. Agent calls the matching skill tool; generation skills run with the conversation's retrieved evidence as grounding.
3. Artifact renders as an inline expandable card; clicking opens the split Artifact Viewer panel; copy/export available.

### Flow C — Recovery
1. Provider error/timeout → structured error event; user retries or switches provider from the composer dropdown (per-message).
2. Unsupported model id (404) → automatic fallback chain, surfaced in `provider_used` metadata.
3. Deleted a session by accident → **Undo** toast restores it within the window; bulk "clear all" requires confirmation.

---

## 3. Acceptance criteria

- [x] Fresh evaluator: `docker compose up --build` (or documented native path) → working app at `localhost:5173` with zero code changes; `.env.example` documents every variable.
- [x] Answers cite transcripts; eval suite (`pytest -m eval`) passes ≥ 90% and runs nightly in CI.
- [x] Off-topic question → genuine refusal, not a nearest-neighbor guess.
- [x] Follow-up ("what about retention?") resolves against conversation context.
- [x] Ship 30 essay artifact is ~1,250 words with hook, progression, skimmable formatting, bolded takeaway (post-conditions asserted; deterministic fallback if the LLM fails).
- [x] HTML artifacts render in a sandboxed iframe with server-side allowlist sanitization; rationale documented.
- [x] Provider switchable per message; Ollama demo works fully offline; Claude Agent SDK path verified end-to-end (tool call → retrieval → grounded answer).
- [x] 107 backend tests green in CI; structured logs + `/api/health` show db/provider status.
- [x] Sessions CRUD with undo-delete; conversations persist in PostgreSQL (SQLite fallback).

---

## 4. Implementation plan (as executed)

| Phase | Deliverable |
|---|---|
| 1 — Core RAG | Ingestion, ChromaDB, retrieval tool, streaming chat, sessions (SQLite) |
| 2 — Skills | PRD / pre-mortem / growth audit / essay / artifact tools + inline cards |
| 3 — Trust | Relevance cutoff + refusal, bge + cross-encoder rerank, eval suite + nightly CI |
| 4 — Product polish | Themes, adaptive width, undo-delete, filter chips, query contextualization |
| 5 — Operations | PostgreSQL migration + Docker Compose, provider telemetry, Claude Agent SDK backend, sandboxing, docs |
