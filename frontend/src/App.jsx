import React, { useState, useEffect, useRef, useCallback } from 'react';
import {
  Sidebar,
  WelcomeScreen,
  ChatMessage,
  ThinkingIndicator,
  ChatInput,
  ArtifactPanel,
  CitationModal,
  Toast,
  Icons,
} from './components/ChatComponents';
import {
  getHealth,
  getConfig,
  listSessions,
  createSession,
  getSession,
  sendMessageStream,
  deleteSession,
  deleteAllSessions,
} from './services/api';

/**
 * Main Application Shell v2.0
 * Orchestrates real-time SSE streaming, multi-agent artifacts, citations, and follow-ups.
 */
export default function App() {
  // ── State ──────────────────────────────────────────
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [sessions, setSessions] = useState([]);
  const [activeSessionId, setActiveSessionId] = useState(null);
  const [messages, setMessages] = useState([]);
  const [artifacts, setArtifacts] = useState([]);
  const [isLoading, setIsLoading] = useState(false);
  const [statusText, setStatusText] = useState('Searching transcripts & composing response…');
  const [activeArtifact, setActiveArtifact] = useState(null);
  const [inspectedCitation, setInspectedCitation] = useState(null);

  // Streaming State
  const [streamingMessage, setStreamingMessage] = useState(null);

  // Provider state
  const [providers, setProviders] = useState([
    { id: 'ollama', label: 'Ollama (Local Llama 3.2)', configured: true },
    { id: 'groq', label: 'Groq Cloud (GPT-OSS 120B)', configured: false },
    { id: 'gemini', label: 'Google Gemini 3.6', configured: false },
    { id: 'mock', label: 'Instant Mock Engine', configured: true },
  ]);
  const [activeProvider, setActiveProvider] = useState('ollama');
  const [providerStatus, setProviderStatus] = useState('healthy');

  // Toast
  const [toasts, setToasts] = useState([]);
  const toastIdRef = useRef(0);

  const chatContainerRef = useRef(null);

  // ── Toast helper ───────────────────────────────────
  const addToast = useCallback((message, type = 'error', extra = {}) => {
    const id = ++toastIdRef.current;
    setToasts((prev) => [...prev, { id, message, type, ...extra }]);
  }, []);

  const removeToast = useCallback((id) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  // ── Scroll to bottom ──────────────────────────────
  // Sticky-scroll: only follows the stream if the user is already near the
  // bottom, so reading/scrolling up during generation is never interrupted.
  const scrollToBottom = useCallback((force = false) => {
    requestAnimationFrame(() => {
      const el = chatContainerRef.current;
      if (!el) return;
      const distanceFromBottom = el.scrollHeight - el.scrollTop - el.clientHeight;
      if (force || distanceFromBottom < 140) {
        el.scrollTop = el.scrollHeight;
      }
    });
  }, []);

  // ── Boot: load config & sessions ──────────────────
  useEffect(() => {
    async function boot() {
      try {
        const [configData, healthData] = await Promise.all([
          getConfig().catch(() => null),
          getHealth().catch(() => null),
        ]);

        if (configData?.available_providers) {
          setProviders(configData.available_providers);
          setActiveProvider(configData.active_provider || 'ollama');
        }

        if (healthData?.llm_provider?.status) {
          setProviderStatus(healthData.llm_provider.status);
        }

        const sessionsData = await listSessions().catch(() => []);
        setSessions(sessionsData);
      } catch (err) {
        addToast('Connected with local fallback mode.', 'info');
      }
    }
    boot();
  }, [addToast]);

  // ── Load session messages when active session changes ──
  useEffect(() => {
    if (!activeSessionId) {
      setMessages([]);
      setArtifacts([]);
      setStreamingMessage(null);
      return;
    }

    async function loadSession() {
      try {
        const data = await getSession(activeSessionId);
        setMessages(data.messages || []);
        setArtifacts(data.artifacts || []);
        setStreamingMessage(null);
        scrollToBottom();
      } catch (err) {
        addToast('Failed to load conversation.', 'error');
      }
    }
    loadSession();
  }, [activeSessionId, addToast, scrollToBottom]);

  // ── Handlers ───────────────────────────────────────
  const handleNewChat = async () => {
    try {
      const newSession = await createSession('New Growth Conversation', activeProvider);
      setSessions((prev) => [
        { id: newSession.id, title: newSession.title, created_at: newSession.created_at, provider_used: newSession.provider_used, message_count: 0 },
        ...prev,
      ]);
      setActiveSessionId(newSession.id);
      setMessages([]);
      setArtifacts([]);
      setActiveArtifact(null);
      setStreamingMessage(null);
    } catch (err) {
      addToast('Failed to create conversation.', 'error');
    }
  };

  const handleSelectSession = (sessionId) => {
    setActiveSessionId(sessionId);
    setActiveArtifact(null);
  };

  // Deferred single-delete with undo: the row vanishes immediately, but the
  // real API delete fires only after the undo window (6s) expires.
  // Timeouts are tracked per-session so rapid successive deletes stay independent.
  const pendingDeleteTimeoutsRef = useRef(new Map());

  const handleDeleteSession = (sessionId) => {
    const deletedSession = sessions.find((s) => s.id === sessionId);
    if (!deletedSession) return;

    const wasActive = activeSessionId === sessionId;
    setSessions((prev) => prev.filter((s) => s.id !== sessionId));
    if (wasActive) {
      setActiveSessionId(null);
      setMessages([]);
      setArtifacts([]);
      setActiveArtifact(null);
    }

    addToast('Conversation deleted', 'info', {
      duration: 6000,
      action: {
        label: 'Undo',
        onClick: () => {
          const pending = pendingDeleteTimeoutsRef.current.get(sessionId);
          if (pending) {
            clearTimeout(pending);
            pendingDeleteTimeoutsRef.current.delete(sessionId);
          }
          setSessions((prev) => {
            if (prev.some((s) => s.id === sessionId)) return prev;
            return [deletedSession, ...prev];
          });
          if (wasActive) setActiveSessionId(sessionId);
        },
      },
    });

    const timeout = setTimeout(async () => {
      pendingDeleteTimeoutsRef.current.delete(sessionId);
      try {
        await deleteSession(sessionId);
      } catch (err) {
        addToast('Failed to delete conversation.', 'error');
      }
    }, 6000);
    pendingDeleteTimeoutsRef.current.set(sessionId, timeout);
  };

  const handleDeleteAllSessions = async () => {
    try {
      await deleteAllSessions();
      setSessions([]);
      setActiveSessionId(null);
      setMessages([]);
      setArtifacts([]);
      setActiveArtifact(null);
      setStreamingMessage(null);
      addToast('All conversations deleted', 'info');
    } catch (err) {
      addToast('Failed to delete conversations.', 'error');
    }
  };

  const handleSendMessage = async (content) => {
    let sessionId = activeSessionId;
    if (!sessionId) {
      try {
        const newSession = await createSession('New Growth Conversation', activeProvider);
        setSessions((prev) => [
          { id: newSession.id, title: newSession.title, created_at: newSession.created_at, provider_used: newSession.provider_used, message_count: 0 },
          ...prev,
        ]);
        sessionId = newSession.id;
        setActiveSessionId(sessionId);
      } catch (err) {
        addToast('Failed to create conversation.', 'error');
        return;
      }
    }

    const tempUserMsg = {
      id: `user-${Date.now()}`,
      role: 'user',
      content,
      sources: [],
      timestamp: new Date().toISOString(),
    };
    setMessages((prev) => [...prev, tempUserMsg]);
    setIsLoading(true);
    setStatusText('Thinking & querying transcripts...');
    
    // Initialize streaming assistant message placeholder
    let streamedText = '';
    let streamedSources = [];
    let streamedArtifacts = [];
    let streamedFollowUps = [];

    setStreamingMessage({
      id: 'streaming-asst',
      role: 'assistant',
      content: '',
      sources: [],
      artifacts: [],
      follow_ups: []
    });
    scrollToBottom();

    try {
      await sendMessageStream(
        sessionId,
        content,
        activeProvider,
        (event) => {
          if (event.type === 'status') {
            setStatusText(event.status || 'Composing response…');
          } else if (event.type === 'tool_start') {
            setStatusText(`Executing PM Tool: ${event.tool}…`);
          } else if (event.type === 'sources') {
            streamedSources = event.sources || [];
            setStreamingMessage((prev) => prev ? { ...prev, sources: streamedSources } : null);
          } else if (event.type === 'artifacts') {
            streamedArtifacts = event.artifacts || [];
            setStreamingMessage((prev) => prev ? { ...prev, artifacts: streamedArtifacts } : null);
            if (streamedArtifacts.length > 0) {
              setActiveArtifact(streamedArtifacts[0]);
            }
          } else if (event.type === 'token') {
            streamedText += event.token || '';
            setStreamingMessage((prev) => prev ? { ...prev, content: streamedText } : null);
            scrollToBottom();
          } else if (event.type === 'done') {
            streamedText = event.full_content || streamedText;
            streamedSources = event.sources || streamedSources;
            streamedArtifacts = event.artifacts || streamedArtifacts;
            streamedFollowUps = event.follow_ups || [];
          } else if (event.type === 'saved') {
            // Finalize message into state
            const finalAssistantMsg = {
              id: event.message_id || `asst-${Date.now()}`,
              role: 'assistant',
              content: streamedText,
              sources: streamedSources,
              artifacts: event.artifacts || streamedArtifacts,
              follow_ups: event.follow_ups || streamedFollowUps,
              timestamp: new Date().toISOString()
            };

            setMessages((prev) => [...prev, finalAssistantMsg]);
            if (event.artifacts?.length > 0) {
              setArtifacts((prev) => [...prev, ...event.artifacts]);
            }
            setStreamingMessage(null);
            setIsLoading(false);

            // Update sidebar title
            setSessions((prev) =>
              prev.map((s) => {
                if (s.id === sessionId) {
                  const newTitle = content.split('\n')[0].substring(0, 48);
                  return {
                    ...s,
                    title: s.title === 'New Growth Conversation' ? newTitle : s.title,
                    message_count: (s.message_count || 0) + 2,
                  };
                }
                return s;
              })
            );
            scrollToBottom();
          }
        },
        (err) => {
          addToast(err.message || 'Streaming failed. Check connection.', 'error');
          setIsLoading(false);
          setStreamingMessage(null);
        }
      );
    } catch (err) {
      addToast(err.message || 'Failed to send message.', 'error');
      setIsLoading(false);
      setStreamingMessage(null);
    }
  };

  const handlePromptClick = (text) => {
    handleSendMessage(text);
  };

  const handleFollowUpClick = (prompt) => {
    handleSendMessage(prompt);
  };

  const handleCitationClick = (source) => {
    setInspectedCitation(source);
  };

  const handleArtifactClick = (artifact) => {
    setActiveArtifact(artifact);
  };

  const handleProviderChange = (providerId) => {
    setActiveProvider(providerId);
    addToast(`Switched active provider to ${providerId.toUpperCase()}`, 'info');
  };

  // ── Current session title for header ───────────────
  const activeSession = sessions.find((s) => s.id === activeSessionId);
  const headerTitle = activeSession?.title || 'Lenny Growth Assistant';

  const getProviderBadgeLabel = () => {
    if (activeProvider === 'ollama') return 'Ollama (Local)';
    if (activeProvider === 'groq') return 'Groq (GPT-OSS)';
    if (activeProvider === 'gemini') return 'Gemini 3.6';
    return 'Mock Engine';
  };

  // ── Render ─────────────────────────────────────────
  return (
    <div className="app-layout">
      {/* Sidebar */}
      <Sidebar
        collapsed={!sidebarOpen}
        sessions={sessions}
        activeSessionId={activeSessionId}
        onNewChat={handleNewChat}
        onSelectSession={handleSelectSession}
        onDeleteSession={handleDeleteSession}
        onDeleteAllSessions={handleDeleteAllSessions}
        providers={providers}
        activeProvider={activeProvider}
        onProviderChange={handleProviderChange}
        providerStatus={providerStatus}
      />

      {/* Main Chat Area */}
      <div className="main-area">
        <header className="main-header">
          {sidebarOpen && (
            <button
              className="sidebar-scrim"
              onClick={() => setSidebarOpen(false)}
              aria-label="Close sidebar"
            />
          )}
          <div className={`main-header-spacer ${sidebarOpen ? 'open' : ''}`} />
          <button
            className="sidebar-toggle"
            onClick={() => setSidebarOpen((v) => !v)}
            id="sidebar-toggle"
            title="Toggle sidebar"
          >
            <Icons.Menu />
          </button>
          <span className="main-header-title">{headerTitle}</span>
          <span className="main-header-badge">
            {getProviderBadgeLabel()}
          </span>
        </header>

        <div className="chat-container" id="chat-container" ref={chatContainerRef}>
          {messages.length === 0 && !isLoading && !streamingMessage ? (
            <WelcomeScreen onPromptClick={handlePromptClick} />
          ) : (
            <div className="chat-messages">
              {messages.map((msg) => (
                <ChatMessage
                  key={msg.id}
                  message={msg}
                  onArtifactClick={handleArtifactClick}
                  onFollowUpClick={handleFollowUpClick}
                  onCitationClick={handleCitationClick}
                  onToast={addToast}
                />
              ))}

              {/* Streaming Live Message */}
              {streamingMessage && (
                <ChatMessage
                  key="streaming"
                  message={streamingMessage}
                  onArtifactClick={handleArtifactClick}
                  onCitationClick={handleCitationClick}
                  isStreaming={true}
                />
              )}

              {isLoading && !streamingMessage?.content && (
                <ThinkingIndicator statusText={statusText} />
              )}

              <div aria-hidden="true" />
            </div>
          )}
        </div>

        <ChatInput
          onSend={handleSendMessage}
          isLoading={isLoading}
          disabled={false}
        />
      </div>

      {/* Artifact Split Pane */}
      <ArtifactPanel
        artifact={activeArtifact}
        onClose={() => setActiveArtifact(null)}
        onToast={addToast}
      />

      {/* Citation Inspector Modal */}
      {inspectedCitation && (
        <CitationModal
          source={inspectedCitation}
          onClose={() => setInspectedCitation(null)}
        />
      )}

      {/* Toasts */}
      <div className="toast-container">
        {toasts.map((t) => (
          <Toast
            key={t.id}
            message={t.message}
            type={t.type}
            duration={t.duration}
            action={t.action}
            onDismiss={() => removeToast(t.id)}
          />
        ))}
      </div>
    </div>
  );
}
