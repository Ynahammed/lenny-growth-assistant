/**
 * API Service Layer for Lenny Growth Assistant.
 * Handles all HTTP & SSE streaming communication with the FastAPI backend.
 */

const API_BASE = '/api';

class ApiError extends Error {
  constructor(message, status, data) {
    super(message);
    this.status = status;
    this.data = data;
    this.name = 'ApiError';
  }
}

async function request(url, options = {}) {
  const config = {
    headers: {
      'Content-Type': 'application/json',
      ...options.headers,
    },
    ...options,
  };

  try {
    const response = await fetch(`${API_BASE}${url}`, config);

    if (response.status === 204) {
      return null;
    }

    const data = await response.json();

    if (!response.ok) {
      throw new ApiError(
        data.detail || `Request failed with status ${response.status}`,
        response.status,
        data
      );
    }

    return data;
  } catch (err) {
    if (err instanceof ApiError) throw err;
    throw new ApiError(
      err.message || 'Network error. Is the backend running on port 8001?',
      0,
      null
    );
  }
}

/** Health check */
export async function getHealth() {
  return request('/health');
}

/** Get public config (providers list) */
export async function getConfig() {
  return request('/config');
}

/** List all chat sessions */
export async function listSessions() {
  return request('/chat/sessions');
}

/** Create a new chat session */
export async function createSession(title = 'New Growth Conversation', provider = null) {
  return request('/chat/sessions', {
    method: 'POST',
    body: JSON.stringify({ title, provider }),
  });
}

/** Get a session with full messages and artifacts */
export async function getSession(sessionId) {
  return request(`/chat/sessions/${sessionId}`);
}

/** Send a message to a session (standard non-streaming) */
export async function sendMessage(sessionId, content, provider = null) {
  return request(`/chat/sessions/${sessionId}/messages`, {
    method: 'POST',
    body: JSON.stringify({ content, provider }),
  });
}

/**
 * Send a message and stream response via Server-Sent Events (SSE).
 * @param {string} sessionId
 * @param {string} content
 * @param {string} provider
 * @param {function} onEvent - Callback for SSE events (token, status, tool_start, sources, artifacts, done)
 * @param {function} onError - Callback for errors
 */
export async function sendMessageStream(sessionId, content, provider = null, onEvent, onError) {
  try {
    const response = await fetch(`${API_BASE}/chat/sessions/${sessionId}/messages/stream`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ content, provider }),
    });

    if (!response.ok) {
      const errJson = await response.json().catch(() => ({}));
      throw new Error(errJson.detail || `Stream failed with status ${response.status}`);
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder('utf-8');
    let buffer = '';

    while (true) {
      const { value, done } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop(); // Keep incomplete trailing fragment

      for (const line of lines) {
        const trimmed = line.trim();
        if (trimmed.startsWith('data: ')) {
          try {
            const data = JSON.parse(trimmed.slice(6));
            if (onEvent) onEvent(data);
          } catch (e) {
            console.error('Failed to parse SSE event:', trimmed, e);
          }
        }
      }
    }
  } catch (err) {
    if (onError) onError(err);
    else throw err;
  }
}

/** Delete a session */
export async function deleteSession(sessionId) {
  return request(`/chat/sessions/${sessionId}`, {
    method: 'DELETE',
  });
}

/** Delete ALL sessions (bulk) */
export async function deleteAllSessions() {
  return request('/chat/sessions', {
    method: 'DELETE',
  });
}

/** Get a single artifact */
export async function getArtifact(artifactId) {
  return request(`/artifacts/${artifactId}`);
}

/** Generate an artifact (essay, html, markdown) */
export async function generateArtifact({
  sessionId,
  messageId = null,
  topic,
  sourceContent = null,
  artifactType = 'essay',
  targetAudience = 'Product Managers and Growth Leads',
}) {
  return request('/artifacts/generate', {
    method: 'POST',
    body: JSON.stringify({
      session_id: sessionId,
      message_id: messageId,
      topic,
      source_content: sourceContent,
      artifact_type: artifactType,
      target_audience: targetAudience,
    }),
  });
}
