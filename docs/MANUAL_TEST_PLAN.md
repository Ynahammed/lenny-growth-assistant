# Manual Test Plan — UI & End-to-End

Complements the automated suite (`pytest`, `-m eval`, CI). Run through these by hand before
demoing or after any frontend change. **Time: ~10 minutes.** Requires the app running —
`docker compose up --build` (recommended) or the native dev path from the README.

> ✅ = expected result. All steps use the default provider unless noted; switch providers from
> the composer's "MODEL PROVIDER" dropdown at any time without losing your draft.

## 1. Welcome & layout

| # | Action | Expected |
|---|---|---|
| 1.1 | Open `http://localhost:5173` | Welcome screen: kicker, 4 example prompt cards, 2 artifact cards (PRD / Pre-Mortem), sidebar with session list, corpus stats footer |
| 1.2 | Click **New Strategy Session** | Fresh empty chat; a new session appears in the sidebar and is highlighted as active |
| 1.3 | Toggle the Sun/Moon button (sidebar header) | Theme flips dark ↔ cream; reload the page — the choice persists |
| 1.4 | Narrow the window to ~800px, then very wide (~2000px) | Sidebar and artifact panel adapt; long answers keep a readable measure (no edge-to-edge text) |

## 2. Grounded Q&A (core loop)

| # | Action | Expected |
|---|---|---|
| 2.1 | Ask: *"How did Rahul Vohra measure PMF at Superhuman?"* (Ollama with `qwen2.5:7b-instruct`, or Groq) | Status shows tool activity; answer streams token-by-token; **citation pills** appear (guest + episode) |
| 2.2 | Click a citation pill | Full transcript excerpt opens with guest/episode metadata |
| 2.3 | Ask a follow-up: *"what about retention?"* | The follow-up is contextualized (tool args/log show the rewritten query) and answered within the same topic context |
| 2.4 | Ask something off-corpus: *"What's the best pizza in Chicago?"* | A **genuine refusal** — no forced nearest-neighbor answer |
| 2.5 | Enable a guest filter chip (e.g. *Gustaf Alströmer*) then ask a growth question | Answers constrain to that guest's episodes; diacritic-insensitive ("Alstromer" also resolves) |

## 3. Artifacts

| # | Action | Expected |
|---|---|---|
| 3.1 | Ask: *"Write a PRD for frictionless self-serve onboarding"* | An inline **artifact card** appears under the answer (panel does NOT auto-open) |
| 3.2 | Click the artifact card | The split **Artifact Viewer** opens beside the chat with the rendered PRD |
| 3.3 | Ask: *"Write an essay about measuring product-market fit"* | Essay artifact generated (~1,250 words); the card footer shows word count metadata; skimmable headings/bold present |
| 3.4 | Use **Copy** in the artifact panel footer | Toast confirms; clipboard contains the markdown |

## 4. Sessions & recovery

| # | Action | Expected |
|---|---|---|
| 4.1 | Hover a session row → delete it | Row disappears; an **Undo toast** appears — click Undo within the window → session restored |
| 4.2 | Delete another session and *let the toast expire* | Deletion is permanent; session does not return on reload |
| 4.3 | Click **Clear all** | Confirmation is required; after confirm, sidebar is empty and DB rows are gone |
| 4.4 | Reload the page | Sessions and message history persist (PostgreSQL) |

## 5. Resilience

| # | Action | Expected |
|---|---|---|
| 5.1 | Switch provider to **Mock** and send a message | Instant canned response — works with zero keys |
| 5.2 | Switch to **Groq** (requires `GROQ_API_KEY` in `backend/.env`) | Real streamed answer; provider label updates per message |
| 5.3 | (Optional) Stop the db container (`docker compose stop db`) then send a message | Structured error, not a crash; restart db and the app recovers on next use |
| 5.4 | Check `/api/health` | Shows db status, vector-store chunk count, and per-provider telemetry |

## 6. Security smoke check (artifacts are untrusted)

| # | Action | Expected |
|---|---|---|
| 6.1 | Via the API: `POST /api/artifacts/generate` with `artifact_type: "html"` and content containing `<script>alert(1)</script>` and `<img src=x onerror=alert(1)>` | Saved artifact contains **no** `<script>`/`onerror` (server sanitizer stripped them) |
| 6.2 | Open that HTML artifact in the viewer | Renders inside the sandboxed iframe; no script executes even if something slipped through |

---

*Report bugs as: step #, provider, provider telemetry from `/api/health`, and the relevant lines
from `docker compose logs backend`.*
