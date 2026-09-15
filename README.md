# Lenny Growth Assistant

A conversational growth & product strategy assistant grounded **exclusively** in Lenny's Podcast
transcripts. Ask a question and a multi-tool agent retrieves relevant transcript evidence,
synthesizes a cited answer, and can generate PRDs, pre-mortems, growth audits, and atomic
essays — streamed token-by-token into a polished chat UI.

Built with **FastAPI + ChromaDB + SQLAlchemy** on the backend and **React 18 + Vite** on the
frontend. Four pluggable LLM providers (local Ollama, Groq, Google Gemini, and an offline Mock)
with automatic model-retirement fallback and per-provider telemetry.

## Documentation

- [PRD.md](PRD.md) — discovery brief, success metrics, assumptions, scope, flows, acceptance criteria
- [design.md](design.md) — UI/UX principles, interaction states, responsive behavior, accessibility, artifact-viewer security rationale
- [architecture.md](architecture.md) — schema, API surface, retrieval flow, agent backends, security model, deployment topology
- [agent_transcripts/](agent_transcripts/TRANSCRIPTS.md) — curated coding-agent session log: failures, dead ends, and how each was fixed (with captured HTTP evidence)

## Features

- **Grounded RAG chat** — every answer is retrieved from the transcript corpus and cited by
  guest and episode number; off-domain questions are refused
- **Six agent tools** — transcript retrieval, PRD generator, Shreyas Doshi pre-mortem simulator,
  growth/funnel audit, Ship 30/30 atomic essay, styled HTML artifact generator
- **Real-time SSE streaming** — status updates, tool activity, tokens, sources, and artifacts
  stream into the UI live
- **Multi-provider** — swap providers (even per message) from the sidebar; keys stay server-side
- **Resilience** — if a provider retires a model (HTTP 404), the app auto-discovers an available
  model and retries transparently
- **Observability** — `/api/health` reports per-provider request/error/fallback counts, latency,
  and token estimates
- **Conversation management** — persistent sessions, per-session delete with undo, bulk
  clear-all, auto-titling from the first message
- **Metadata filtering** — constrain retrieval to a specific guest or episode via UI chips;
  user-pinned filters override whatever the LLM guesses
- **Query contextualization** — vague follow-ups ("what about retention?") are rewritten with
  conversation context before embedding; self-contained questions skip the rewrite
- **Chocolate Truffle themes** — dark cocoa and cream light mode from one palette, toggled in
  the sidebar and persisted per browser

## Quick start

### Prerequisites

- Python 3.12
- Node.js 18+
- Docker (for the bundled PostgreSQL; or point `DATABASE_URL` at Supabase/Railway)
- (optional) [Ollama](https://ollama.com) with a model pulled, e.g. `ollama pull llama3.2`

### One-command startup (Docker Compose)

Brings up PostgreSQL + backend + frontend together:

```bash
docker compose up --build
docker compose ps          # all services healthy
# open http://localhost:5173 — /api proxies to the backend container
```

LLM keys are read from `backend/.env` (Compose loads it automatically). Existing conversations in
the old SQLite file can be carried over with `python scripts/migrate_sqlite_to_postgres.py`
(from `backend/`).

### Backend

```bash
cd backend
pip install -r requirements.txt
cp .env.example .env        # then edit .env with your API keys (see below)
python -m uvicorn app.main:app --port 8001
```

On startup the app connects to **PostgreSQL** (the default `DATABASE_URL` points at
`localhost:5432` with lenny/lenny credentials — start it with `docker compose up -d db`, or point
`DATABASE_URL` at Supabase/Railway, or set `DATABASE_URL=sqlite:///lenny_growth.db` for a SQLite
fallback) and indexes the bundled transcripts into ChromaDB if the vector store is empty. Health
check:

```bash
curl http://127.0.0.1:8001/api/health
```

### Frontend

```bash
cd frontend
npm install
npm run dev                 # http://localhost:5173 (proxies /api -> 127.0.0.1:8001)
```

### Run the tests

```bash
cd backend
python -m pytest            # 72 tests; uses isolated temp DB/vector store
```

### Groundedness eval

A 33-case eval set (`backend/tests/eval/`) scores what unit tests can't: does retrieval
surface the *right* episode, do citations rank the right guest first, and do off-domain
questions actually get refused. It runs the real embedding + reranking pipeline against a
fresh temp vector store (never touches the dev index).

```bash
cd backend
python -m tests.eval.runner             # report; exit 1 below thresholds
python -m tests.eval.runner --show-all  # per-case detail with cosine scores
python -m pytest -m eval                # same suite as a slow pytest marker
```

Current baseline: **97% overall** (refusal 10/10, citation 6/6, retrieval 16/17) with
refusals gated at 100% — a single leak fails the suite. The one known retrieval gap is the
documented `hxc_segment` case: jargon-only phrasings can land ~0.02 below the refusal gate
(lowering the gate would break off-topic refusal; adding context to the query fixes it).
Re-run the eval after any retrieval, embedding-model, or cutoff change.

A nightly GitHub Actions job (`.github/workflows/nightly-eval.yml`, 03:30 UTC, also
manually triggerable) runs the suite against `main` so retrieval regressions surface
automatically; on failure it re-runs the runner with `--show-all` to print the full report.

## Provider configuration

Configure in `backend/.env` (never commit this file). Current model defaults reflect vendor
catalogs as of September 2026 — older defaults (gemini-1.5-flash, llama-3.3-70b) were retired.

| Provider | Env vars | Notes |
|---|---|---|
| **Ollama** (default) | `OLLAMA_BASE_URL`, `OLLAMA_MODEL` | Fully local/offline; needs `ollama serve` |
| **Groq** | `GROQ_API_KEY`, `GROQ_MODEL` | Ultra-fast cloud inference; default `openai/gpt-oss-120b` |
| **Gemini** | `GEMINI_API_KEY`, `GEMINI_MODEL` | Default `gemini-3.6-flash`; supports tool calling + SSE |
| **Mock** | — | Deterministic offline answers for zero-setup testing/CI |

Set the default with `LLM_PROVIDER=ollama|groq|gemini|mock`. The frontend dropdown can switch
providers per session (or per message) regardless of the default.

**Grounded-refusal cutoff:** retrieval drops chunks whose bi-encoder cosine similarity
scores below `RELEVANCE_CUTOFF` (default `0.62`, calibrated for `bge-small-en-v1.5`).
On this corpus on-topic queries score 0.66–0.81 while off-topic ones (recipes, sports,
weather) stay under 0.58 — so off-topic questions get a genuine refusal rather than an
answer forced from the nearest neighbors. Raise it to demand stricter grounding, or set
`0` to restore classic nearest-neighbor behavior.

**Embeddings + reranking:** chunks are indexed with `BAAI/bge-small-en-v1.5` (384-dim,
query-prefixed for asymmetric retrieval) via sentence-transformers. At query time the top
`RERANK_CANDIDATES` candidates that clear the gate are re-ordered by a cross-encoder
(`cross-encoder/ms-marco-MiniLM-L-6-v2`) so answer-bearing excerpts surface first — the
cross-encoder orders but never admits chunks, since it scores conversational transcript
excerpts low even when they're topically relevant. Changing `EMBEDDING_MODEL` auto-reindexes
the vector store on next use (the model name is stored in collection metadata); models
download to the local HF cache on first run.

**Query contextualization:** vague follow-ups ("what about retention?", "tell me more")
embed poorly on their own, so before retrieval they are rewritten into self-contained
search queries using the recent conversation. Self-contained questions skip the rewrite
entirely (no extra LLM call); the rewrite LLM failing degrades to deterministic stitching
of the last user message onto the follow-up. Guest/episode filter chips still apply to the
rewritten query, and user-pinned filters always win.

**Model retirement auto-fallback:** every provider is wrapped in an `InstrumentedProvider` that
detects model-not-found errors, queries the provider's catalog, ranks candidates
(gpt-oss > llama > qwen > gemini …), switches, and retries — so a vendor retiring a model
degrades instead of breaking.

## The agent tools

The LLM decides which tool to call (OpenAI-style function calling across providers):

| Tool | Purpose |
|---|---|
| `retrieve` | Bi-encoder search + cross-encoder rerank over the transcript vector store; returns cited chunks with guest/episode metadata |
| `prd_generator` | Production-grade PRD: problem statement, HXC persona, goals/metrics, user stories, non-goals, rollout plan |
| `pre_mortem_simulator` | Shreyas Doshi-style pre-mortem: failure modes, mitigations, go/no-go checklist |
| `growth_audit` | Funnel/activation/retention diagnosis with benchmarks and experiment suggestions |
| `ship30_essay` | ~1,250-word Ship 30 for 30 atomic essay (hook → subheaded progression → bolded takeaway), with word-budget post-conditions and a deterministic evidence-only fallback |
| `artifact_gen` | Styled shareable artifact (markdown or sanitized HTML document) |

Tool flow: the model may call `retrieve` first (collecting sources), then answer — sources are
rendered as clickable citation pills that open the full transcript excerpt.

## Agent backends (Claude Agent SDK + native loop)

The agent layer ships with **two interchangeable backends**, selected with `AGENT_BACKEND`:

| Backend | Value | Notes |
|---|---|---|
| **Claude Agent SDK** (default) | `claude-agent-sdk` | The six tools are re-exported as **in-process MCP tools** (`create_sdk_mcp_server`) and the official Anthropic SDK drives the tool loop via its bundled Claude Code CLI |
| **Native loop** | `native` | `AgentManager`'s own provider-agnostic function-calling loop (works with every provider, incl. Groq/Gemini/mock) |

- **Provider routing:** the SDK path supports providers with an Anthropic-Messages-compatible
  endpoint — `ollama` (verified live: `ANTHROPIC_BASE_URL` = Ollama origin, model discovery via
  `/v1/models`) and `anthropic`. Groq/Gemini have no such endpoint and automatically use the
  native loop.
- **Graceful fallback:** any SDK failure (missing CLI, subprocess error, unsupported provider)
  falls back to the native loop *before the first streamed event*, so the product never breaks.
- **Shared executor:** both backends call the same `_execute_tool`, so filters, contextualized
  queries, sources, and artifacts behave identically either way.
- **Compatibility notes** (found the hard way, encoded in `sdk_adapter.py`): the CLI appends
  `/v1/messages` itself (base URL must be the bare origin), custom model ids need
  `CLAUDE_CODE_ENABLE_GATEWAY_MODEL_DISCOVERY=1`, and CLI-injected `system`-role reminder
  messages are disabled (`CLAUDE_CODE_TOTAL_TOKENS_REMINDER=0`,
  `CLAUDE_CODE_CARVED_SLATE=0`) because they break tool binding on small local models.
- Small local models (≤3B) often skip tool calls entirely; `qwen2.5:7b-instruct` or larger is
  recommended for the SDK + Ollama path.

## Architecture

```
frontend (React 18 + Vite, port 5173)
  │   /api proxy
  ▼
backend FastAPI (port 8001)
  ├── routes/chat.py        sessions CRUD, messages, SSE streaming, bulk delete
  ├── routes/artifacts.py   artifact generation (essay/html/markdown)
  ├── agents/agent_manager  tool orchestration loop + streaming event generator
  ├── llm/provider.py       Ollama / Groq / Gemini / Mock providers
  ├── llm/telemetry.py      InstrumentedProvider: metrics + 404 model fallback
  ├── agents/tools/         6 tool executors + JSON schemas
  ├── ingestion/ingest.py   transcript parsing, chunking, ChromaDB indexing
  ├── database/             SQLAlchemy models: sessions, messages, artifacts
  └── middleware/           structured JSON logging, global error handlers
        │
        ├── PostgreSQL (default; Docker/Supabase/Railway)   sessions / messages / artifacts
        │   └── SQLite fallback via DATABASE_URL=sqlite:///...
        └── ChromaDB (chroma_db/)        48 transcript chunks, cited metadata
```

**Streaming protocol (SSE events):** `status` → `tool_start` / `tool_end` → `sources` →
`artifacts` → `token`* → `done` → `saved` (persisted message IDs).

### Adding transcripts

Drop `.txt`/`.md` files with optional YAML-ish frontmatter into
`backend/app/ingestion/transcripts/`:

```
---
guest: Jane Doe
episode_title: The Growth Episode
episode_number: 42
topic_tags: growth, loops
---
Transcript body...
```

Then re-index:

```bash
cd backend
python -m app.ingestion.ingest --reset
```

## Security notes

- **Generated HTML artifacts are untrusted.** They pass an allowlist sanitizer (`nh3` — scripts,
  event handlers, `javascript:` URLs, iframes, and CSS `@import`/`url()` are stripped) *before*
  persistence, and render in a sandboxed iframe (no scripts, no forms, no popups, no app-origin
  access). The full permit/block rationale is in [design.md](design.md) §Security.
- CORS is wide open (`allow_origins=["*"]`) and there is **no authentication** — fine for local
  use; lock both down before exposing beyond localhost
- API keys live only in `backend/.env`, which is git-ignored
