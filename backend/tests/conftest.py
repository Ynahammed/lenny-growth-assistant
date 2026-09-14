"""Shared pytest fixtures: isolated SQLite DB, real ChromaDB, mock provider."""
import os
import tempfile

import pytest

_tmp = tempfile.mkdtemp(prefix="lenny_test_")
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp}/test.db"
os.environ["CHROMA_PERSIST_DIRECTORY"] = os.path.join(_tmp, "chroma")
os.environ["GROQ_API_KEY"] = ""
os.environ["GEMINI_API_KEY"] = ""
os.environ["LLM_PROVIDER"] = "mock"

from fastapi.testclient import TestClient

from app.main import app
from app.database.db import init_db
from app.database.models import SessionModel, MessageModel, ArtifactModel
from app.database.db import SessionLocal
from app.llm.provider import LLMProvider, LLMResponse, ToolCall, get_provider
import app.llm.provider as provider_module
import app.routes.chat as chat_routes
import app.routes.artifacts as artifacts_routes
from app.llm.telemetry import telemetry


@pytest.fixture(scope="session", autouse=True)
def _init_db():
    init_db()
    yield


@pytest.fixture(autouse=True)
def _reset_telemetry():
    telemetry.reset()
    yield
    telemetry.reset()


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


class StubProvider(LLMProvider):
    """Scriptable provider stub for routing and agent tests."""

    def __init__(self, responses=None, name="stub"):
        self.responses = list(responses or [])
        self.calls = []
        self._name = name

    @property
    def provider_name(self):
        return self._name

    @property
    def model_name(self):
        return "stub-model"

    async def check_health(self):
        return {"status": "healthy", "provider": self._name}

    async def generate(self, messages, system_prompt, tools=None, **kwargs):
        self.calls.append({"messages": messages, "tools": tools})
        if not self.responses:
            return LLMResponse(content="ok", provider=self._name, model="stub-model")
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        if isinstance(item, str):
            return LLMResponse(content=item, provider=self._name, model="stub-model")
        return item

    async def generate_stream(self, messages, system_prompt, tools=None, **kwargs):
        for word in "hello world".split():
            yield word + " "


@pytest.fixture
def stub_provider():
    return StubProvider()


@pytest.fixture
def patch_provider_factory(monkeypatch):
    """Swap the stub LLM into route handlers, keeping real agent orchestration."""
    from app.agents.agent_manager import AgentManager as RealAgentManager

    def _patch(provider):
        class PatchedAgentManager(RealAgentManager):
            def __init__(self, provider_type=None):
                super().__init__(provider_type=provider_type)
                self.provider = provider

        monkeypatch.setattr(chat_routes, "AgentManager", PatchedAgentManager)
        monkeypatch.setattr(artifacts_routes, "get_provider", lambda *a, **k: provider)

    return _patch


@pytest.fixture
def session_id(client):
    resp = client.post("/api/chat/sessions", json={"title": "Test Session"})
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


@pytest.fixture
def message_with_sources(client, session_id, stub_provider, patch_provider_factory):
    """Send one message with a tool call and sources, returning message id."""
    stub = StubProvider(responses=[
        LLMResponse(
            content="",
            tool_calls=[ToolCall(id="call_1", name="retrieve", arguments={"query": "pmf"})],
            provider="stub", model="stub-model",
        ),
        LLMResponse(
            content="Grounded answer citing Rahul Vohra.",
            provider="stub", model="stub-model",
        ),
    ])
    patch_provider_factory(stub)
    resp = client.post(
        f"/api/chat/sessions/{session_id}/messages",
        json={"content": "How did Rahul measure PMF?"},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["assistant_message"]["id"]


@pytest.fixture
def cleanup_sessions():
    """Remove sessions created during a test (by title prefix)."""
    created = []

    def _track(sid):
        created.append(sid)

    yield _track

    db = SessionLocal()
    try:
        for sid in created:
            sess = db.query(SessionModel).filter(SessionModel.id == sid).first()
            if sess:
                db.delete(sess)
        db.commit()
    finally:
        db.close()
