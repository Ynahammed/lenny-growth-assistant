import React, { useState, useEffect } from 'react';
import ReactMarkdown from 'react-markdown';

/**
 * Icons used throughout the app (inline SVG components for zero-dependency icons).
 */
export const Icons = {
  Sun: () => (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="4" />
      <path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M4.93 19.07l1.41-1.41M17.66 6.34l1.41-1.41" />
    </svg>
  ),
  Moon: () => (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M21 12.79A9 9 0 1111.21 3 7 7 0 0021 12.79z" />
    </svg>
  ),
  Logo: () => (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 2L2 7l10 5 10-5-10-5z" />
      <path d="M2 17l10 5 10-5" />
      <path d="M2 12l10 5 10-5" />
    </svg>
  ),
  Plus: () => (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
      <line x1="12" y1="5" x2="12" y2="19" />
      <line x1="5" y1="12" x2="19" y2="12" />
    </svg>
  ),
  Send: () => (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <line x1="22" y1="2" x2="11" y2="13" />
      <polygon points="22 2 15 22 11 13 2 9 22 2" />
    </svg>
  ),
  User: () => (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
      <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" />
      <circle cx="12" cy="7" r="4" />
    </svg>
  ),
  Bot: () => (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 2L2 7l10 5 10-5-10-5z" />
      <path d="M2 17l10 5 10-5" />
      <path d="M2 12l10 5 10-5" />
    </svg>
  ),
  Chat: () => (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
      <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
    </svg>
  ),
  Menu: () => (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
      <line x1="3" y1="6" x2="21" y2="6" />
      <line x1="3" y1="12" x2="21" y2="12" />
      <line x1="3" y1="18" x2="21" y2="18" />
    </svg>
  ),
  X: () => (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
      <line x1="18" y1="6" x2="6" y2="18" />
      <line x1="6" y1="6" x2="18" y2="18" />
    </svg>
  ),
  Trash: () => (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
      <polyline points="3 6 5 6 21 6" />
      <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
    </svg>
  ),
  ChevronDown: () => (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
      <polyline points="6 9 12 15 18 9" />
    </svg>
  ),
  FileText: () => (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
      <polyline points="14 2 14 8 20 8" />
      <line x1="16" y1="13" x2="8" y2="13" />
      <line x1="16" y1="17" x2="8" y2="17" />
    </svg>
  ),
  Bookmark: () => (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
      <path d="M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z" />
    </svg>
  ),
  Sparkles: () => (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 3l1.5 4.5L18 9l-4.5 1.5L12 15l-1.5-4.5L6 9l4.5-1.5L12 3z" />
      <path d="M19 15l.88 2.62L22.5 18.5l-2.62.88L19 22l-.88-2.62L15.5 18.5l2.62-.88L19 15z" />
    </svg>
  ),
  Copy: () => (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
      <rect x="9" y="9" width="13" height="13" rx="2" ry="2" />
      <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
    </svg>
  ),
  Check: () => (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
      <polyline points="20 6 9 17 4 12" />
    </svg>
  ),
  Download: () => (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
      <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
      <polyline points="7 10 12 15 17 10" />
      <line x1="12" y1="15" x2="12" y2="3" />
    </svg>
  ),
  Search: () => (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
      <circle cx="11" cy="11" r="8" />
      <line x1="21" y1="21" x2="16.65" y2="16.65" />
    </svg>
  ),
};


/**
 * Sidebar component with session list and provider selector.
 */
export function Sidebar({
  collapsed,
  sessions,
  activeSessionId,
  onNewChat,
  onSelectSession,
  onDeleteSession,
  onDeleteAllSessions,
  providers,
  activeProvider,
  onProviderChange,
  providerStatus,
  corpus,
  theme,
  onToggleTheme,
}) {
  const [confirmClearAll, setConfirmClearAll] = useState(false);
  const [confirmDeleteId, setConfirmDeleteId] = useState(null);
  return (
    <aside className={`sidebar ${collapsed ? 'collapsed' : ''}`}>
      <div className="sidebar-header">
        <div className="sidebar-logo">
          <Icons.Logo />
        </div>
        <div className="sidebar-brand">
          <h1>Lenny Growth</h1>
          <span className="sidebar-badge">v2.0 · Live</span>
        </div>
        <button
          className="theme-toggle"
          onClick={onToggleTheme}
          title={theme === 'cream' ? 'Switch to dark cocoa' : 'Switch to cream'}
          aria-label="Toggle color theme"
        >
          {theme === 'cream' ? <Icons.Moon /> : <Icons.Sun />}
        </button>
      </div>

      <div className="sidebar-action">
        <button className="new-chat-btn" onClick={onNewChat} id="new-chat-btn">
          <Icons.Plus />
          <span>New Strategy Session</span>
        </button>
      </div>

      <div className="sidebar-section-title">Model Provider</div>
      <div className="provider-selector-card">
        <select
          className="provider-select"
          value={activeProvider}
          onChange={(e) => onProviderChange(e.target.value)}
          id="provider-select"
        >
          {providers.map((p) => (
            <option key={p.id} value={p.id}>
              {p.label}
            </option>
          ))}
        </select>
        <div className="provider-meta">
          <span className={`status-dot ${providerStatus}`} />
          <span className="status-text">
            {activeProvider === 'ollama' && 'Local Offline (Zero Telemetry)'}
            {activeProvider === 'groq' && 'Cloud GPT-OSS 120B (ultra-fast)'}
            {activeProvider === 'gemini' && 'Google Gemini 3.6 Flash'}
            {activeProvider === 'mock' && 'Instant Offline Mock'}
          </span>
        </div>
      </div>

      <div className="sidebar-section-title sessions-header">
        <span>Recent Conversations</span>
        {sessions.length > 0 && (
          <button
            className={`clear-all-btn ${confirmClearAll ? 'confirm' : ''}`}
            onClick={() => {
              if (confirmClearAll) {
                onDeleteAllSessions?.();
                setConfirmClearAll(false);
              } else {
                setConfirmClearAll(true);
                // Auto-cancel the confirmation after 4s
                setTimeout(() => setConfirmClearAll(false), 4000);
              }
            }}
            onBlur={() => setConfirmClearAll(false)}
            title={confirmClearAll ? 'Click again to permanently delete all conversations' : 'Delete all conversations'}
          >
            {confirmClearAll ? 'Sure?' : 'Clear all'}
          </button>
        )}
      </div>
      <div className="sessions-list">
        {sessions.length === 0 ? (
          <div className="empty-sessions">No saved conversations yet</div>
        ) : (
          sessions.map((s) => (
            <div
              key={s.id}
              className={`session-item ${s.id === activeSessionId ? 'active' : ''}`}
              onClick={() => onSelectSession(s.id)}
              id={`session-${s.id}`}
            >
              <div className="session-icon">
                <Icons.Chat />
              </div>
              <div className="session-title">{s.title || 'Untitled Session'}</div>
              <button
                className={`session-delete ${confirmDeleteId === s.id ? 'confirm' : ''}`}
                onClick={(e) => {
                  e.stopPropagation();
                  if (confirmDeleteId === s.id) {
                    onDeleteSession(s.id);
                    setConfirmDeleteId(null);
                  } else {
                    setConfirmDeleteId(s.id);
                    setTimeout(() => setConfirmDeleteId((cur) => (cur === s.id ? null : cur)), 3500);
                  }
                }}
                onBlur={() => setConfirmDeleteId((cur) => (cur === s.id ? null : cur))}
                title={confirmDeleteId === s.id ? 'Click again to delete this conversation' : 'Delete conversation'}
              >
                {confirmDeleteId === s.id ? 'Sure?' : <Icons.Trash />}
              </button>
            </div>
          ))
        )}
      </div>

      <div className="sidebar-footer">
        <div className="corpus-info">
          <span className="corpus-icon">🎧</span>
          <div className="corpus-text">
            <strong>Lenny Transcript Corpus</strong>
            <span>
              {corpus?.episodes?.length
                ? `${corpus.episodes.length} Episodes · ${corpus.total_chunks} Indexed Chunks`
                : 'Loading corpus…'}
            </span>
          </div>
        </div>
      </div>
    </aside>
  );
}


/**
 * Welcome screen shown when no messages exist.
 */
export function WelcomeScreen({ onPromptClick }) {
  const prompts = [
    {
      label: '⚡ Prioritization',
      text: "Explain Shreyas Doshi's LNO framework for task prioritization.",
    },
    {
      label: '🎯 Superhuman PMF',
      text: "How did Rahul Vohra build the quantitative Product-Market Fit engine for Superhuman?",
    },
    {
      label: '🔄 Growth Loops',
      text: "Why are growth loops superior to traditional marketing funnels in marketplaces?",
    },
    {
      label: '🧩 Jobs to be Done',
      text: "What are Bob Moesta's 4 Forces of Progress in purchasing decisions?",
    },
    {
      label: '📄 Generate PRD',
      text: "Generate a comprehensive PRD for a frictionless self-serve onboarding flow.",
    },
    {
      label: '🔮 Run Pre-Mortem',
      text: "Run a Shreyas Doshi Pre-Mortem on our upcoming self-serve enterprise tier launch.",
    },
  ];

  return (
    <div className="welcome-screen">
      <div className="welcome-icon">
        <Icons.Sparkles />
      </div>
      <div className="welcome-kicker">Grounded in 10 podcast episodes</div>
      <h2>What do you want to figure out?</h2>
      <p>
        Product and growth strategy grounded exclusively in Lenny's Podcast transcripts —
        Shreyas Doshi, Rahul Vohra, Casey Winters, Elena Verna, Gustaf Alströmer, Bob Moesta —
        with citations for every claim.
      </p>
      <div className="welcome-prompts">
        {prompts.map((p, i) => (
          <button
            key={i}
            className="welcome-prompt"
            onClick={() => onPromptClick(p.text)}
            id={`welcome-prompt-${i}`}
          >
            <span className="prompt-label">{p.label}</span>
            <span className="prompt-body">{p.text}</span>
          </button>
        ))}
      </div>
    </div>
  );
}


/**
 * Suggested follow-up prompt chips rendered below assistant messages.
 */
export function FollowUpPills({ followUps, onSelect }) {
  if (!followUps || followUps.length === 0) return null;

  return (
    <div className="follow-ups-container">
      <div className="follow-ups-label">
        <Icons.Sparkles /> Suggested Follow-Ups:
      </div>
      <div className="follow-ups-list">
        {followUps.map((prompt, idx) => (
          <button
            key={idx}
            className="follow-up-pill"
            onClick={() => onSelect(prompt)}
          >
            {prompt}
          </button>
        ))}
      </div>
    </div>
  );
}


/**
 * 1-Click Copy and Export action bar.
 */
export function ActionBar({ content, title, onToast }) {
  const [copied, setCopied] = useState(false);

  const handleCopyMarkdown = async () => {
    try {
      await navigator.clipboard.writeText(content);
      setCopied(true);
      if (onToast) onToast('Copied Markdown to clipboard!', 'success');
      setTimeout(() => setCopied(false), 2000);
    } catch (err) {
      if (onToast) onToast('Failed to copy', 'error');
    }
  };

  const handleDownload = () => {
    const blob = new Blob([content], { type: 'text/markdown;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${(title || 'lenny-growth-insight').toLowerCase().replace(/[^a-z0-9]+/g, '-')}.md`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
    if (onToast) onToast('Downloaded .md file!', 'success');
  };

  return (
    <div className="message-action-bar">
      <button className="action-btn" onClick={handleCopyMarkdown} title="Copy Markdown">
        {copied ? <Icons.Check /> : <Icons.Copy />}
        <span>{copied ? 'Copied' : 'Copy'}</span>
      </button>
      <button className="action-btn" onClick={handleDownload} title="Download as .md">
        <Icons.Download />
        <span>Export .md</span>
      </button>
    </div>
  );
}


/**
 * Modal to inspect full transcript source context.
 */
export function CitationModal({ source, onClose }) {
  if (!source) return null;

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-container" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <div className="modal-badge-row">
            <span className="modal-guest-badge">{source.guest || 'Lenny Guest'}</span>
            <span className="modal-ep-badge">Ep #{source.episode_number || '–'}</span>
          </div>
          <button className="modal-close-btn" onClick={onClose}>
            <Icons.X />
          </button>
        </div>
        <h3 className="modal-title">{source.episode_title || 'Episode Transcript'}</h3>
        {source.topic_tags && (
          <div className="modal-tags">
            <strong>Tags:</strong> {source.topic_tags}
          </div>
        )}
        <div className="modal-body">
          <div className="modal-section-label">Verified Podcast Transcript Excerpt:</div>
          <div className="modal-excerpt-text">{source.excerpt}</div>
        </div>
        <div className="modal-footer">
          <span className="modal-source-file">{source.source_file || 'Transcript Corpus'}</span>
          <button className="modal-action-btn" onClick={onClose}>
            Close
          </button>
        </div>
      </div>
    </div>
  );
}


/**
 * Single chat message with avatar, streaming cursor, sources, follow-ups, and artifacts.
 */
export function ChatMessage({
  message,
  onArtifactClick,
  onFollowUpClick,
  onCitationClick,
  onToast,
  isStreaming = false
}) {
  const [expandedArtifacts, setExpandedArtifacts] = useState({});

  const toggleArtifact = (artId) => {
    setExpandedArtifacts((prev) => ({ ...prev, [artId]: !prev[artId] }));
  };

  const isUser = message.role === 'user';
  const sources = message.sources || [];
  const artifacts = message.artifacts || [];
  const followUps = message.follow_ups || [];

  return (
    <div className={`message ${isUser ? 'from-user' : 'from-assistant'}`} id={`msg-${message.id || 'streaming'}`}>
      {isUser ? (
        <div className="message-bubble user-bubble">
          {message.content}
        </div>
      ) : (
        <div className="message-body">
          <div className="message-role assistant">Lenny Assistant</div>
          <div className="message-content">
            <ReactMarkdown>{message.content}</ReactMarkdown>
            {isStreaming && <span className="streaming-cursor">▋</span>}
          </div>

        {/* Source Citation Pills */}
        {sources.length > 0 && (
          <div className="message-sources">
            <span className="sources-label">Grounded Sources:</span>
            {sources.map((src, idx) => (
              <button
                className="source-chip clickable"
                key={idx}
                onClick={() => onCitationClick && onCitationClick(src)}
                title="Click to inspect full transcript excerpt"
              >
                <span className="source-number">{idx + 1}</span>
                <span className="source-guest">{src.guest || `Source ${idx + 1}`}</span>
                {src.episode_number ? <span className="source-ep">Ep #{src.episode_number}</span> : null}
              </button>
            ))}
          </div>
        )}

        {/* Generated Artifacts */}
        {artifacts.length > 0 && (
          <div className="message-artifacts">
            {artifacts.map((art, idx) => (
              <div className="artifact-card" key={art.id || idx}>
                <div
                  className="artifact-card-header"
                  onClick={() => {
                    if (onArtifactClick) {
                      onArtifactClick(art);
                    } else {
                      toggleArtifact(art.id || idx);
                    }
                  }}
                >
                  <span className={`artifact-type-badge ${art.artifact_type || 'markdown'}`}>
                    {art.artifact_type || 'artifact'}
                  </span>
                  <span className="artifact-card-title">{art.title}</span>
                  <span className={`artifact-expand-icon ${expandedArtifacts[art.id || idx] ? 'expanded' : ''}`}>
                    <Icons.ChevronDown />
                  </span>
                </div>
                <div className={`artifact-card-body ${expandedArtifacts[art.id || idx] ? 'expanded' : ''}`}>
                  <div className="artifact-content">
                    {isHtmlArtifact(art) ? (
                      <SandboxHtmlArtifact html={art.content} />
                    ) : (
                      <ReactMarkdown>{art.content}</ReactMarkdown>
                    )}
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}

        {/* Follow-up suggestions */}
        {!isStreaming && followUps.length > 0 && (
          <FollowUpPills followUps={followUps} onSelect={onFollowUpClick} />
        )}

        {/* Action bar for copying/exporting */}
        {!isUser && !isStreaming && message.content && (
          <ActionBar content={message.content} title="lenny-growth-insight" onToast={onToast} />
        )}
        </div>
      )}
    </div>
  );
}


/**
 * Thinking indicator showing live tool status.
 */
export function ThinkingIndicator({ statusText = 'Searching transcripts & composing response…' }) {
  return (
    <div className="thinking-indicator">
      <div className="message-avatar assistant">
        <Icons.Bot />
      </div>
      <div>
        <div className="thinking-dots">
          <span /><span /><span />
        </div>
        <div className="thinking-text">{statusText}</div>
      </div>
    </div>
  );
}


/**
 * Chat input area with auto-resizing textarea.
 */
export function ChatInput({ onSend, isLoading, disabled }) {
  const [value, setValue] = useState('');
  const textareaRef = React.useRef(null);

  const handleSubmit = () => {
    const trimmed = value.trim();
    if (!trimmed || isLoading) return;
    onSend(trimmed);
    setValue('');
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  const handleInput = (e) => {
    setValue(e.target.value);
    const el = e.target;
    el.style.height = 'auto';
    el.style.height = Math.min(el.scrollHeight, 160) + 'px';
  };

  const hasContent = value.trim().length > 0;

  return (
    <div className="input-area">
      <div className="input-wrapper">
        <div className="input-box">
          <textarea
            ref={textareaRef}
            className="input-textarea"
            placeholder="Ask about PMF engines, LNO framework, growth loops, or ask for a PRD..."
            value={value}
            onChange={handleInput}
            onKeyDown={handleKeyDown}
            rows={1}
            disabled={isLoading || disabled}
            id="chat-input"
          />
          <button
            className={`send-btn ${hasContent ? 'active' : ''}`}
            onClick={handleSubmit}
            disabled={!hasContent || isLoading || disabled}
            id="send-btn"
            title="Send message"
          >
            <Icons.Send />
          </button>
        </div>
        <div className="input-hint">
          <kbd>Enter</kbd> to stream response · <kbd>Shift+Enter</kbd> for new line · 100% Grounded
        </div>
      </div>
    </div>
  );
}


/**
 * Retrieval filter chips: constrain answers to one guest or episode.
 * Renders nothing while corpus metadata is unavailable/empty.
 */
export function FilterChips({ corpus, guest, episode, onChange, disabled }) {
  if (!corpus || (!corpus.guests?.length && !corpus.episodes?.length)) return null;

  const hasFilter = Boolean(guest || episode);

  return (
    <div className="filter-chips-row" aria-label="Retrieval filters">
      <span className="filter-chips-label">Search only</span>

      <select
        className="filter-chip"
        value={guest || ''}
        disabled={disabled}
        onChange={(e) => onChange({ guest: e.target.value || null, episode })}
        title="Restrict retrieval to one guest"
      >
        <option value="">All guests</option>
        {corpus.guests.map((g) => (
          <option key={g} value={g}>{g}</option>
        ))}
      </select>

      <select
        className="filter-chip filter-chip-episode"
        value={episode || ''}
        disabled={disabled}
        onChange={(e) => onChange({ guest, episode: e.target.value ? Number(e.target.value) : null })}
        title="Restrict retrieval to one episode"
      >
        <option value="">All episodes</option>
        {corpus.episodes.map((ep) => (
          <option key={ep.episode_number} value={ep.episode_number}>
            #{ep.episode_number} · {ep.guest}
          </option>
        ))}
      </select>

      {hasFilter && (
        <button
          className="filter-chip-clear"
          onClick={() => onChange({ guest: null, episode: null })}
          title="Clear filters"
        >
          <Icons.X />
          Clear
        </button>
      )}
    </div>
  );
}/**
 * Sandbox for untrusted HTML artifacts.
 *
 * Why both an attribute allowlist AND a sandbox: the sandbox isolates the
 * document (no app DOM/origin/storage access, no scripts, no popups, no form
 * submissions); the attribute allowlist is the second layer, covering any
 * content that reaches the real DOM (e.g. copy/export paths). Only
 * https:/mailto: links survive; inline styles remain so generated documents
 * keep their design.
 */
const HTML_ARTIFACT_SANDBOX = 'allow-same-origin';

export function SandboxHtmlArtifact({ html }) {
  return (
    <iframe
      className="artifact-html-frame"
      title="Artifact preview"
      sandbox={HTML_ARTIFACT_SANDBOX}
      srcDoc={html}
      referrerPolicy="no-referrer"
    />
  );
}

export function isHtmlArtifact(artifact) {
  if (!artifact) return false;
  const t = artifact.artifact_type || '';
  if (t === 'html') return true;
  return t === 'markdown' && /<\s*(html|body|!DOCTYPE)[\s>]/i.test(artifact.content || '');
}

/**
 * Artifact viewer panel (split view on the right).
 */
export function ArtifactPanel({ artifact, onClose, onToast }) {
  if (!artifact) return <div className="artifact-panel" />;

  return (
    <div className="artifact-panel open">
      <div className="artifact-panel-header">
        <span className={`artifact-type-badge ${artifact.artifact_type || 'markdown'}`}>{artifact.artifact_type || 'artifact'}
        </span>
        <span className="artifact-panel-title">{artifact.title}</span>
        <button className="artifact-panel-close" onClick={onClose} id="close-artifact-panel">
          <Icons.X />
        </button>
      </div>
      <div className="artifact-panel-body">
        {isHtmlArtifact(artifact) ? (
          <SandboxHtmlArtifact html={artifact.content} />
        ) : (
          <div className="rendered-markdown">
            <ReactMarkdown>{artifact.content}</ReactMarkdown>
          </div>
        )}
      </div>
      <div className="artifact-panel-footer">
        <ActionBar content={artifact.content} title={artifact.title} onToast={onToast} />
      </div>
    </div>
  );
}


/**
 * Toast notification component.
 */
export function Toast({ message, type = 'error', onDismiss, action, duration = 4000 }) {
  useEffect(() => {
    const timer = setTimeout(() => onDismiss?.(), duration);
    return () => clearTimeout(timer);
  }, [onDismiss, duration]);

  return (
    <div className={`toast ${type}`} onClick={action ? undefined : onDismiss}>
      <span className="toast-message">{type === 'error' ? '⚠' : '✓'} {message}</span>
      {action && (
        <button
          className="toast-action"
          onClick={(e) => {
            e.stopPropagation();
            action.onClick?.();
            onDismiss?.();
          }}
        >
          {action.label}
        </button>
      )}
    </div>
  );
}
