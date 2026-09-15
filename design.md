# Design — The Lenny Growth Assistant

UI/UX principles, information architecture, key states, and the security/design rationale
behind the artifact viewer.

---

## 1. Design principles

1. **The answer is the hero.** Every chrome element (sidebar, chips, badges) is visually
   quieter than the assistant's answer. Long-form answers get adaptive measure
   (max-width scales with viewport) and a readable type ramp, because the primary content
   is multi-paragraph prose, not cards.
2. **Trust is a feature.** Citations (guest / episode / quote) are first-class UI, the
   relevance refusal is communicated as *what the corpus does cover*, and provider/model
   provenance is shown per message. Nothing pretends to know more than the corpus.
3. **States are explicit.** Streaming, tool-running, refusing, error, and empty states are
   all visibly distinct — the user always knows *why* the assistant is doing what it's doing.
4. **One palette, two surfaces.** A single Chocolate Truffle palette powers both themes:
   dark (cocoa `#17100a→#2f2218`, caramel `#C05800` accents, cream `#FDFBD4` text) and
   cream (roles inverted; accent deepens to `#713600` for contrast on light surfaces).
   Theme choice persists via `localStorage` and applies before first paint.
5. **Accessibility beats decoration.** Keyboard-reachable controls, focus styles, native
   controls via `color-scheme`, contrast-checked status colors, reduced-motion-friendly
   streaming cursor.

## 2. Information architecture

```
┌────────────┬──────────────────────────────────┬───────────────┐
│  Sidebar   │  Chat column                     │ Artifact Panel│
│            │                                  │ (split view)  │
│ New chat   │  Welcome screen (empty state):   │               │
│ ─────────  │   kicker + value proposition     │ header: type  │
│ Sessions   │   4 example prompt cards         │  badge, title │
│ (rename,   │   with concrete tasks            │  close        │
│  delete,   │                                  │ body: HTML →  │
│  undo)     │  Message thread:                 │  sandboxed    │
│ ─────────  │   role avatar · adaptive-width   │  iframe; else │
│ Corpus     │   bubble · citation pills ·      │  markdown     │
│ stats      │   inline artifact cards ·        │ footer: copy/ │
│ Theme      │   follow-up pills · action bar   │  export       │
│ toggle     │  Composer: model picker + chips  │               │
└────────────┴──────────────────────────────────┴───────────────┘
```

- **Sessions sidebar** is the only global navigation; the chat column owns the rest.
- **Filter chips** (guest/episode) live beside the composer because they modify *the next
  question*, not the app.
- **Artifacts** appear inline (expandable card) so the reading flow never breaks; the panel
  opens only on deliberate click — never auto-popped mid-stream.

## 3. Key interaction states

| State | Design behavior |
|---|---|
| **Welcome (empty)** | No fake chat transcript; kicker + prompt cards teach the grounded-workflow in one glance |
| **Streaming** | Token-by-token text with a pulsing caret; `status` events show "querying transcripts…" |
| **Tool running** | Distinct `tool_start` pill (e.g. `retrieve`) so the user sees *why* latency exists |
| **Refusal** | Plain-language refusal + pointer to covered topics — never a silent empty answer |
| **Sources** | Citation pills under the answer; click → full transcript excerpt with guest/episode metadata |
| **Artifact** | Inline expandable card; click → split Artifact Viewer; copy/export in the panel footer |
| **Error** | Inline structured error with retry affordance; provider switchable from the composer without losing the draft |
| **Delete** | Destructive actions confirm (bulk) or offer **Undo** within a window (single) — toast carries the restore action |

## 4. Responsive behavior

- **≥ 1280px**: three-zone layout (sidebar / chat / artifact panel opens as a third column).
- **768–1279px**: artifact panel overlays the chat column (slide-in) rather than squeezing
  the reading measure; chat bubble max-width stays prose-friendly.
- **< 768px**: sidebar collapses to a drawer; composer remains thumb-reachable; artifact
  panel becomes a full-screen sheet with a sticky close button.
- Long answers keep a measure of ~65–75ch on wide screens via adaptive width, so lines
  never run edge-to-edge on ultrawide monitors.

## 5. Accessibility considerations

- Semantic headings inside rendered answers (`#`/`###` map to real h1/h3 in markdown render).
- Icon-only controls (theme toggle, close, copy) expose `aria-label`s.
- Focus outlines visible in both themes (caramel on dark, chocolate on cream).
- `color-scheme` set per theme so native scrollbars/inputs/selects match.
- Status never conveyed by color alone (badges carry text labels).
- prefers-reduced-motion: streaming caret and toasts drop non-essential animation.

## 6. The artifact viewer — decisions & security rationale

**Why a split panel, not a modal or new tab:** artifacts are meant to be read *next to* the
conversation that produced them (compare, iterate, ask follow-ups). A modal hides the chat;
a new tab breaks the session's visual context. The inline card + deliberate panel-open keeps
flow: preview → expand → focus.

**Why the default render is markdown and HTML gets an iframe:** markdown artifacts are
structured text (headings, bullets, code) that ReactMarkdown renders with zero execution
risk. HTML artifacts are complete documents meant to be *styled* — inline CSS must survive,
but scripts must not. That split is what the two render paths express.

**Security — what is permitted, what is blocked, and why.** Generated HTML is treated as
**untrusted** (it is model output, and prompts can be injected through retrieved text):

| Layer | Permitted | Blocked | Why |
|---|---|---|---|
| **Server sanitizer (nh3 allowlist)** before persistence | headings, paragraphs, lists, tables, links (`http/https/mailto`), images, `<style>` (inline CSS), inline `style=` attributes | `<script>`, event handlers (`on*`), `javascript:`/`data:` URLs, `<iframe>`/`<object>`/`<embed>`, external resource loads (`@import`/`url()` in CSS) | An allowlist parser (not regex) survives mXSS/attribute-splitting evasion; styled documents still render as designed |
| **Client sandbox (`<iframe sandbox="allow-same-origin" srcDoc>`)** | static HTML/CSS rendering, layout, links open with `noopener noreferrer` and `no-referrer` | **scripts** (no `allow-scripts`), form submission, popups, app-origin DOM/storage access, top-navigation | Even if a payload survived sanitization, the sandbox denies it any power: it cannot read the app's DOM, tokens, or storage, and cannot execute code |
| **Defense in depth** | — | — | The two layers fail differently (parser escape vs. sandbox escape) and are independently testable; either alone is considered insufficient for untrusted content |

Links are additionally forced `rel="noopener noreferrer"` server-side, and the iframe sets
`referrerPolicy="no-referrer"` so artifacts can't leak the app's URL as a referrer.

**Known trade-off:** scripts can never run, so artifacts can't include interactive JS
(quiz widgets, live charts). For this product's artifacts (documents, frameworks, memos),
static fidelity is the requirement; interactivity would require a build/serve pipeline and a
larger trust boundary — out of scope and documented as such.
