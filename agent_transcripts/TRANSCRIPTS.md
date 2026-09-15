# Agent Transcripts — Curated Session Log

Curated excerpts from the coding-agent (Freebuff/Buffy) sessions that built this project,
**including failed attempts and how each was corrected**, as required by the assignment.
Raw evidence files live in `captures/` (secrets scanned/absent; auth tokens are
placeholders — Ollama requires no key).

The single most instructive thread: **integrating the Claude Agent SDK with a local
Ollama model**. It took five sequential discoveries, each proven with captured HTTP
evidence, before the first successful end-to-end tool call.

---

## Session 1 — Claude Agent SDK × Ollama (the hard one)

**Goal:** satisfy the "must use the Claude Agent SDK or Pi Coding Agent" requirement
without giving up Groq/Ollama flexibility — the SDK's bundled CLI only speaks the
Anthropic Messages API.

### Failure 1 — `/v1/v1/messages` (misreported as a model error)
- **Symptom:** CLI failed with `[claude-code:unrecognized_model]` for a model that Ollama
  definitely serves.
- **Investigation:** pointed the CLI at a logging HTTP proxy; captured
  `captures/01-title-request.json` and replayed it directly against Ollama.
- **Finding:** with `ANTHROPIC_BASE_URL=http://localhost:11434/v1`, the CLI requested
  **`/v1/v1/messages`** — path doubled. Ollama 404'd, and the CLI classified the 404 as
  "model not recognized".
- **Fix:** base URL must be the **bare origin**. Locked in by a regression test
  (`test_resolve_routing_ollama_uses_anthropic_compat_endpoint`).

### Failure 2 — custom model ids rejected by the CLI's hardcoded catalog
- **Symptom:** `unrecognized_model` persisted even with the correct URL.
- **Fix:** `CLAUDE_CODE_ENABLE_GATEWAY_MODEL_DISCOVERY=1` — the CLI then discovers models
  from `{base_url}/v1/models` (Ollama serves this) instead of validating against Anthropic's
  catalog.

### Failure 3 — CLI-injected `system`-role message breaks tool binding
- **Symptom:** the turn completed but the local model *never called tools*, while an
  equivalent raw HTTP request with the same system prompt did (`stop_reason: tool_use`).
- **Investigation:** captured the CLI's actual turn request
  (`captures/02-turn-request-with-reminder.json`). Diff vs. the working raw request: the CLI
  appends a **role:"system" message** ("`<total_tokens>…`" context-usage notice) — invalid
  under the Anthropic schema, mishandled by Ollama's compat layer, and it suppressed tool
  binding. Verified by bisect: the same payload *without* that message binds tools.
- **Fix:** `CLAUDE_CODE_TOTAL_TOKENS_REMINDER=0` in the adapter's subprocess env.

### Failure 4 — `<system-reminder>` preamble (carved-slate injection)
- **Symptom:** with the reminder disabled, tool calls were still rare.
- **Investigation:** strings-grepped the 220MB bundled `claude.exe`; found
  `CLAUDE_CODE_CARVED_SLATE` adjacent to the "As you answer the user's questions… Today's
  date…" template. Capture with the flag off confirmed the preamble disappears
  (`captures/03-turn-request-no-reminder.json`).
- **Honest correction:** a 3×3 variance replay then showed reminder-free requests **still**
  failed to bind tools — so this flag was *not* the root cause. It stays disabled (cleaner
  prompt) but the real culprit was still missing. Recorded here because discarding the
  hypothesis after the variance test is exactly the kind of negative result that saves the
  next person a day.

### Root cause 5 — the model, not the plumbing
- **Finding:** llama3.2:3b is simply too weak a tool-caller at this prompt size (6 MCP tools
  + long system prompt): across 10+ replays it returned `end_turn` ~90% of the time. A field
  bisect of the entire CLI request (tools, names, metadata, thinking, context_management,
  messages) confirmed **no single field was responsible**.
- **Fix:** pulled `qwen2.5:7b-instruct` → first try: `tool_use` → MCP `retrieve` executed
  in-process → grounded refusal with citation → streamed answer. Documented the ≤3B caveat in
  README and `.env.example`.

**End state:** `AGENT_BACKEND=claude-agent-sdk` (default) runs the full agentic cycle
through the official SDK with Ollama, with automatic fallback to the native loop for
Groq/Gemini/mock or any SDK failure.

---

## Session 2 — Postgres migration surfaced orphaned rows

- **Symptom:** first migration run failed its FK assertions.
- **Finding:** SQLite had **14 messages + 2 artifacts whose parent sessions were already
  deleted** — SQLite doesn't enforce foreign keys unless the pragma is enabled, so historic
  deletes left orphans.
- **Fix:** migration script now skips and *reports* orphans; the SQLite engine sets
  `PRAGMA foreign_keys=ON` (via an engine event hook) so it can't recur. Committed as part
  of the Postgres migration (`56e344a`).

## Session 3 — Ship 30 tool "worked" but never wrote an essay

- **Symptom:** the essay tool returned *instructions* (word budget, format rules) and the
  dispatcher appended `essay_content: ""` — the artifact was always empty, and length was
  250–300 words instead of the required ~1,250.
- **Fix:** rewrote the skill to actually generate via the active provider with encoded Ship
  30 principles and executable post-conditions (1,100–1,400 words, structure, grounded
  takeaway), one bounded expansion round for short drafts, and a deterministic
  evidence-only fallback when the LLM fails. The artifacts route was refactored onto the
  same skill. Regression tests cover the LLM path, the fallback, and the expansion round.

## Session 4 — regex "sanitizer" → real allowlist sanitizer

- **Symptom (audit):** the HTML "sanitizer" was three regexes; classic evasions
  (mXSS, attribute splitting, `<iframe>`, `data:` URLs) sailed through.
- **Fix:** nh3 (Rust ammonia) allowlist sanitization before persistence, with the legacy
  regex pass retained only as an ImportError fallback. Two implementation failures worth
  recording: (1) nh3 1.x doesn't exist on PyPI (installed 0.3.7); (2) nh3 panics if `style`
  appears in both `tags` and `clean_content_tags` — resolved with an explicit
  `clean_content_tags={"script"}` override. XSS vectors are now covered by tests.

## Session 5 — frontend artifacts had no isolation at all

- **Symptom (audit):** all artifacts rendered through ReactMarkdown; HTML artifacts showed
  as raw code (feature broken) — and any future path that rendered them raw had zero
  isolation.
- **Fix:** sandboxed `<iframe sandbox="allow-same-origin" srcDoc>` viewer (no scripts,
  no forms, no popups, no app-origin access; `referrerPolicy="no-referrer"`), dual-mode
  detection, and a documented permit/block rationale (design.md §Security).

---

## What these transcripts show

1. **Hypothesis → capture → prove** debugging: every fix above is backed by a captured
   request or a variance test, not vibes.
2. **Negative results recorded** (the carved-slate red herring) instead of being
   quietly dropped.
3. **Regretted failures converted into regression tests** (base-URL, orphans, XSS vectors,
   essay post-conditions).
4. **Spec-tension judgment calls documented** (SDK only speaks Anthropic-Messages;
   the adapter + native-loop fallback is the resolution, argued in PRD.md §Scope).
