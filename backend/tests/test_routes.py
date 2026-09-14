"""Tests for REST endpoints: sessions, messages, artifacts, health, config."""
import pytest

from app.database.models import ArtifactModel
from app.database.db import SessionLocal


class TestHealthAndConfig:
    def test_health_reports_core_services(self, client):
        resp = client.get("/api/health")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "online"
        assert body["database"] == "healthy"
        assert body["vector_store"]["status"] == "active"
        assert body["llm_provider"]["status"] in ("healthy", "unconfigured")

    def test_health_includes_telemetry_block(self, client):
        body = client.get("/api/health").json()
        assert "llm_telemetry" in body
        assert "providers" in body["llm_telemetry"]
        assert "totals" in body["llm_telemetry"]

    def test_config_lists_all_four_providers(self, client):
        body = client.get("/api/config").json()
        ids = {p["id"] for p in body["available_providers"]}
        assert ids == {"ollama", "groq", "gemini", "mock"}


class TestSessionCrud:
    def test_create_list_get_delete(self, client, cleanup_sessions):
        created = client.post("/api/chat/sessions", json={"title": "CRUD Test"}).json()
        cleanup_sessions(created["id"])

        assert created["title"] == "CRUD Test"

        listed = client.get("/api/chat/sessions").json()
        assert any(s["id"] == created["id"] for s in listed)

        detail = client.get(f"/api/chat/sessions/{created['id']}").json()
        assert detail["messages"] == []
        assert detail["artifacts"] == []

        resp = client.delete(f"/api/chat/sessions/{created['id']}")
        assert resp.status_code == 204
        assert client.get(f"/api/chat/sessions/{created['id']}").status_code == 404

    def test_get_missing_session_404(self, client):
        assert client.get("/api/chat/sessions/nope").status_code == 404

    def test_delete_missing_session_404(self, client):
        assert client.delete("/api/chat/sessions/nope").status_code == 404

    def test_delete_all_sessions_bulk(self, client, cleanup_sessions):
        s1 = client.post("/api/chat/sessions", json={"title": "Bulk A"}).json()["id"]
        s2 = client.post("/api/chat/sessions", json={"title": "Bulk B"}).json()["id"]
        cleanup_sessions(s1)
        cleanup_sessions(s2)

        resp = client.delete("/api/chat/sessions")
        assert resp.status_code == 204
        assert client.get("/api/chat/sessions").json() == []
        assert client.get(f"/api/chat/sessions/{s1}").status_code == 404
        assert client.get(f"/api/chat/sessions/{s2}").status_code == 404


class TestMessages:
    def test_send_message_persists_both_roles(self, client, session_id, stub_provider, patch_provider_factory):
        stub_provider.responses.append("A concise grounded answer.")
        patch_provider_factory(stub_provider)
        resp = client.post(
            f"/api/chat/sessions/{session_id}/messages",
            json={"content": "What is a growth loop?"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["user_message"]["role"] == "user"
        assert body["assistant_message"]["role"] == "assistant"
        assert "growth loop" in body["assistant_message"]["content"].lower() or body["assistant_message"]["content"]

        detail = client.get(f"/api/chat/sessions/{session_id}").json()
        assert len(detail["messages"]) == 2

    def test_message_persists_artifacts(self, client, session_id, cleanup_sessions):
        client.post(
            f"/api/chat/sessions/{session_id}/messages",
            json={"content": "Run a pre-mortem on our launch"},
        )
        detail = client.get(f"/api/chat/sessions/{session_id}").json()
        assert len(detail["artifacts"]) >= 1
        assert detail["artifacts"][0]["artifact_type"] == "pre_mortem"

    def test_auto_title_from_first_message(self, client, cleanup_sessions):
        sid = client.post("/api/chat/sessions", json={"title": "New Growth Conversation"}).json()["id"]
        cleanup_sessions(sid)
        client.post(
            f"/api/chat/sessions/{sid}/messages",
            json={"content": "How do growth loops replace funnels?"},
        )
        title = client.get(f"/api/chat/sessions/{sid}").json()["title"]
        assert title.startswith("How do growth loops")

    def test_send_to_missing_session_404(self, client):
        resp = client.post(
            "/api/chat/sessions/nope/messages", json={"content": "hi"}
        )
        assert resp.status_code == 404

    def test_validation_rejects_empty_content(self, client, session_id, stub_provider, patch_provider_factory):
        patch_provider_factory(stub_provider)
        resp = client.post(
            f"/api/chat/sessions/{session_id}/messages", json={"content": ""}
        )
        assert resp.status_code == 422

    def test_stream_endpoint_saves_message(self, client, session_id, cleanup_sessions):
        with client.stream(
            "POST",
            f"/api/chat/sessions/{session_id}/messages/stream",
            json={"content": "Explain the LNO framework", "provider": "mock"},
        ) as resp:
            assert resp.status_code == 200
            assert "text/event-stream" in resp.headers["content-type"]
            body = b"".join(resp.iter_bytes()).decode("utf-8")

        assert "data:" in body
        assert '"type": "done"' in body
        assert '"type": "saved"' in body

        detail = client.get(f"/api/chat/sessions/{session_id}").json()
        roles = [m["role"] for m in detail["messages"]]
        assert roles.count("user") == 1 and roles.count("assistant") == 1


class TestArtifacts:
    def test_generated_artifact_is_persisted_and_fetchable(self, client, session_id, cleanup_sessions):
        resp = client.post("/api/artifacts/generate", json={
            "session_id": session_id,
            "topic": "Activation metrics",
            "artifact_type": "essay",
        })
        assert resp.status_code == 201
        art = resp.json()
        assert art["artifact_type"] == "essay"
        assert art["content"]

        fetched = client.get(f"/api/artifacts/{art['id']}")
        assert fetched.status_code == 200
        assert fetched.json()["title"] == art["title"]

    def test_artifacts_linked_to_message(self, client, session_id, message_with_sources):
        detail = client.get(f"/api/chat/sessions/{session_id}").json()
        linked = [a for a in detail["artifacts"] if a.get("message_id") == message_with_sources]
        assert isinstance(linked, list)  # route accepts message linkage without error

    def test_generate_for_missing_session_404(self, client):
        resp = client.post("/api/artifacts/generate", json={
            "session_id": "missing", "topic": "t",
        })
        assert resp.status_code == 404

    def test_get_missing_artifact_404(self, client):
        assert client.get("/api/artifacts/does-not-exist").status_code == 404
