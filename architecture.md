# Architecture — The Lenny Growth Assistant

---

## 1. Topology

```
┌────────────────────────────┐        ┌─────────────────────────────────┐
│  Frontend (React 18/Vite)  │  /api  │  Backend (FastAPI, port 8001)   │
│  localhost:5173            │───────▶│                                 │
│  • chat + SSE streaming    │ proxy  │  routes/        REST + SSE      │
│  • artifact viewer         │        │  middleware/    logging, errors │
│    (sandboxed iframe)      │        │  agents/        agent loop(s)   │
└────────────────────────────┘        │  llm/           providers       │
                                      │  rag/           retrieval stack │
                                      │  ingestion/     corpus → Chroma │
                                      │  database/      SQLAlchemy      │
                                      └───────┬───────────────┬─────────┘
                                              │               │
                                   ┌──────────▼──────┐  ┌─────▼──────────────┐
                                   │ PostgreSQL 16   │  │ ChromaDB           │
                                   │ sessions/       │  │ (persist dir)      │
                                   │ messages/       │  │ 48 transcript      │
                                   │ artifacts       │  │ chunks + metadata  │
                                   └─────────────────┘  └────────────────────┘
                                              ▲
                              ┌───────────────┼──────────────────┐
                        ┌─────┴─────┐   ┌─────▼─────┐   ┌────────▼──────┐
                        │ Ollama    │   │ Groq      │   │ Gemini /      │
                        │ (local)   │   │ (cloud)   │   │ Anthropic     │
                        └───────────┘   └───────────┘   └───────────────┘
```

Docker Compose (`docker compose up --build`) brings up **db + backend + frontend** with
healthchecks, an HF model-cache volume, and LLM keys read from `backend/.env`. Native dev
runs the same services by hand (see README §Quick start).

## 2. Database schema (PostgreSQL, SQLAlchemy models)

| Table | Key columns | Notes |
|---|---|---|
| `sessions` | `id` (UUID), `title`, `created_at`, `updated_at`, `provider_used`, `is_archived` | One row per chat; independent context per session |
| `messages` | `id` (UUID), `session_id` → sessions, `role`, `content`, `sources` (JSON), `provider_used`, `model_used`, `created_at` | `sources` holds cited chunks for the turn; FK enforced (also on SQLite via pragma) |
| `artifacts` | `id` (UUID), `session_id` → sessions, `message_id` → messages (nullable), `artifact_type`, `title`, `content`, `created_at` | Rendered by the Artifact Viewer; HTML is sanitized before persistence |

Soft aspects: `DATABASE_URL` defaults to `postgresql+psycopg://…@localhost:5432/lenny_growth`
(Compose credentials); bare `postgres://` URLs (Supabase/Railway) are normalized to the psycopg
driver; SQLite remains an explicit fallback for tests/air-gapped runs. Startup runs `init_db()`
and fails with an actionable message ("run `docker compose up -d db`") if the DB is unreachable.
`scripts/migrate_sqlite_to_postgres.py` moves legacy SQLite data (orphan rows are skipped and
reported — a real bug class the migration surfaced).

## 3. API surface (REST + SSE)

| Method & path | Purpose |
|---|---|
| `POST /api/chat/sessions` | Create session |
| `GET /api/chat/sessions` | List sessions |
| `PATCH /api/chat/sessions/{id}` | Rename / archive |
| `DELETE /api/chat/sessions/{id}` | Delete one (frontend shows undo toast within a window) |
| `POST /api/chat/sessions/delete-all` | Bulk clear (confirm-gated in UI) |
| `GET /api/chat/sessions/{id}/messages` | Transcript of a session |
| `POST /api/chat/{session_id}/stream` | **SSE**: one agent turn — events: `status`, `tool_start`, `tool_end`, `sources`, `artifacts`, `token`, `done`, `saved`, `error` |
| `POST /api/artifacts/generate` | Skill artifact from a session/message (essay/html/markdown) |
| `GET /api/health` | Liveness + db check + provider telemetry (counts, latency, last error, fallbacks) |

Contracts are Pydantic models; validation errors return structured 422s; a global error
handler maps unexpected failures to structured 500 JSON (never stack-trace dumps).

## 4. Component boundaries

- **routes/** — HTTP concerns only: parse/validate, delegate, serialize. No business logic.
- **agents/agent_manager.py** — `AgentManager`: conversation state → tool-calling loop → streamed events. Owns the tool executor (`_execute_tool`) shared by both agent backends.
- **agents/tools/** — one module per skill, each exporting a JSON-schema + an executor. Tools are pure-ish functions: `(args, evidence) → artifact/text`; no HTTP awareness.
- **rag/** — embedding (BAAI/bge-small-en-v1.5 + query instruction), Chroma search, cross-encoder rerank (ms-marco-MiniLM-L-6-v2), cosine gate, query contextualization (LLM rewrite of vague follow-ups with deterministic fallback).
- **llm/** — provider abstraction (`OllamaProvider`, `GroqProvider`, `GeminiProvider`, `AnthropicProvider`, `MockProvider`) + `InstrumentedProvider` wrapper (latency/error counters, 404 model auto-fallback chain).
- **database/** — models + engine/session factory; FK pragma on SQLite.
- **middleware/** — structured JSON logging (request ids), global exception handlers.

## 5. Ingestion & retrieval flow

**Ingestion** (`ingestion/ingest.py`): transcript files in `data/` → parse per speaker-turn →
chunk (~800 tokens, overlap) → embed (bge-small) → persist to ChromaDB with metadata
(`guest`, `episode_title`, `episode_number`, `chunk_id`) so every stored vector traces back to
its source. Refresh = delete + re-run the script (documented in README §Adding transcripts).

**Retrieval** (`agents/tools/retrieve.py` + `rag/`):
1. Query contextualization: vague follow-up? → LLM rewrites with last-6-turn context (self-contained queries skip this entirely; LLM failure → deterministic fallback stitching the previous user message).
2. Bi-encoder search over Chroma (query prefixed with the bge instruction).
3. Cross-encoder rerank of the candidate pool; scores → sigmoid(logit) on 0–1.
4. Cosine gate (0.62): chunks below are dropped. **All dropped → `NO_RELEVANT_EVIDENCE`** → the agent refuses instead of guessing.
5. Surviving chunks are returned with metadata; `guest`/`episode_number` filters (UI chips) constrain the search and are diacritics-normalized ("Alstromer" matches "Alströmer").

## 6. Agent backends (the model-toggle layer)

`AGENT_BACKEND` selects the loop; `LLM_PROVIDER` selects the model behind it. Per-message
provider switching is supported at the API layer; unavailable models 404 → `InstrumentedProvider`
falls back down the provider chain and records the event in telemetry.

| Backend | What runs the tool loop | Providers supported |
|---|---|---|
| **`claude-agent-sdk`** (default) | Official Anthropic SDK; six tools re-exported as in-process MCP tools (`create_sdk_mcp_server`); bundled Claude Code CLI drives the loop | Anthropic-Messages-compatible endpoints only: `anthropic` (native), `ollama` (compat endpoint at `ANTHROPIC_BASE_URL`; model discovery via `/v1/models`) |
| **`native`** | `AgentManager`'s own OpenAI-style function-calling loop | All providers, incl. Groq / Gemini / mock |

Fallback semantics: any SDK failure raises `AdapterError` **before the first streamed event** →
native loop runs transparently; the mock provider (tests) never enters the SDK path. CLI
compatibility findings are encoded in `sdk_adapter.py` (base URL must be the bare origin;
`CLAUDE_CODE_ENABLE_GATEWAY_MODEL_DISCOVERY=1` for custom ids; CLI reminder injections disabled
— they break tool binding on small local models).

## 7. Security model (artifacts & secrets)

**Generated HTML is untrusted** (model output could embed injected payloads):
1. **Server, before persistence** — allowlist sanitizer `nh3` (Rust ammonia): tags/attributes allowlists, URL scheme restriction to `http/https/mailto`, `rel="noopener noreferrer"` forced on links, `<style>` content additionally scrubbed of `@import`/`url()`/`expression()`. Regex fallback exists if nh3 is unavailable (tests cover both paths).
2. **Client, at render** — sandboxed `<iframe sandbox="allow-same-origin" srcDoc=…>`: **no scripts** (no `allow-scripts`), no forms, no popups, no app-origin DOM/storage access; `referrerPolicy="no-referrer"`.
3. Rationale: sandboxing isolates *what sanitization allows*; sanitization shrinks *what the sandbox renders*. Both layers are independently testable; the permit/block table lives in design.md §Security.

Secrets: only `.env` (gitignored; `.env.example` documents every key with empty defaults);
CI/nightly eval run keyless via the mock provider; structured logs never include raw prompts
or keys.

## 8. Observability & resilience

- **Structured JSON logs** with request ids on every route; agent/tool events (`Agent executing tool 'retrieve'…`, rewrite decisions, dropped-chunk counts) are log-greppable.
- **`/api/health`**: `{status, db: {ok, url-safe}, providers: {per-provider call counts, error counts, p50/p95 latency, last error, fallback events}}`.
- **Failure modes handled**: missing keys (provider construction fails fast with a clear message), Ollama down (connection error surfaced as a chat error event, not a crash), model timeouts, 404 unknown-model (auto-fallback chain), empty retrieval (refusal path), DB down (startup guard + health check), malformed tool args (normalized in `_execute_tool`).

## 9. Deployment topology

- **Compose (recommended)**: `db` (postgres:16, healthcheck, volume) + `backend` (python:3.12-slim, libgomp for torch, uvicorn, depends_on db-healthy) + `frontend` (node build → vite preview or dev proxy; target configurable via `VITE_API_PROXY_TARGET`). Shared `.env` for keys; named volumes for Postgres data, Chroma dir, and the HF model cache.
- **Native**: two terminals (uvicorn + vite) against a Compose or managed Postgres.
- **Managed** (Supabase/Railway): set `DATABASE_URL` to the pooled connection string; the URL normalizer handles their `postgres://` format.
