"""Health, validation (422) and error-shape tests."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from tests.conftest import make_settings


def test_health_reports_ok_with_key_pool_and_cache(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["keys_configured"] == 2
    assert body["cache_enabled"] is True


def test_health_is_503_without_keys(tmp_path, provider) -> None:  # type: ignore[no-untyped-def]
    with TestClient(create_app(make_settings(tmp_path, llm_api_keys=""))) as client:
        response = client.get("/health")
    assert response.status_code == 503
    assert "detail" in response.json()


@pytest.mark.parametrize(
    "payload",
    [
        {"message": "hello"},  # missing session_id
        {"session_id": "", "message": "hello"},  # empty session_id
        {"session_id": "   ", "message": "hello"},  # blank session_id
        {"session_id": "s" * 129, "message": "hello"},  # session_id too long
        {"session_id": "s-1"},  # missing message
        {"session_id": "s-1", "message": ""},  # empty message
        {"session_id": "s-1", "message": "   \n\t "},  # whitespace-only message (empty after trim)
        {"session_id": "s-1", "message": "x" * 4001},  # message over 4000 chars
        {"session_id": "s-1", "message": 123},  # wrong type
        {"session_id": 42, "message": "hello"},  # wrong type
    ],
)
def test_invalid_chat_requests_return_422_and_are_not_persisted(client: TestClient, provider, payload) -> None:  # type: ignore[no-untyped-def]
    response = client.post("/chat", json=payload)
    assert response.status_code == 422
    assert "detail" in response.json()
    assert provider.calls == []
    session_id = payload.get("session_id")
    if isinstance(session_id, str) and 0 < len(session_id) <= 128 and session_id.strip():
        assert client.get(f"/sessions/{session_id}/messages").status_code == 404


def test_malformed_json_returns_422(client: TestClient) -> None:
    response = client.post("/chat", content=b'{"session_id": "s-1", "message": ', headers={"Content-Type": "application/json"})
    assert response.status_code == 422
    assert "detail" in response.json()


def test_message_of_exactly_4000_chars_after_trimming_is_accepted(chat) -> None:  # type: ignore[no-untyped-def]
    response = chat("s-limit", "  " + "x" * 4000 + "  ")
    assert response.status_code == 200


def test_message_is_trimmed_before_storage(client: TestClient, chat) -> None:  # type: ignore[no-untyped-def]
    chat("s-trim", "   hello there   ")
    history = client.get("/sessions/s-trim/messages").json()
    assert history["messages"][0]["content"] == "hello there"


def test_unknown_session_history_returns_404(client: TestClient) -> None:
    response = client.get("/sessions/does-not-exist/messages")
    assert response.status_code == 404
    assert response.json() == {"detail": "session not found"}


def test_unknown_route_is_json_not_html(client: TestClient) -> None:
    response = client.get("/nope")
    assert response.status_code == 404
    assert response.headers["content-type"].startswith("application/json")


def test_cors_allows_configured_origin_and_simulation_header(client: TestClient) -> None:
    response = client.options(
        "/chat",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type,x-simulate-failure",
        },
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"


def test_cors_rejects_unknown_origin(client: TestClient) -> None:
    response = client.get("/health", headers={"Origin": "https://evil.example"})
    assert "access-control-allow-origin" not in response.headers


def test_unexpected_server_error_is_clean_json_and_persists_nothing(client: TestClient, provider, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    from app.repository import ChatRepository

    def broken_save(*_args, **_kwargs):  # type: ignore[no-untyped-def]
        raise RuntimeError("disk full: /secret/path")

    monkeypatch.setattr(ChatRepository, "save_turn", broken_save)
    with TestClient(client.app, raise_server_exceptions=False) as raw_client:
        response = raw_client.post("/chat", json={"session_id": "s-500", "message": "hi"})
    assert response.status_code == 500
    assert response.json() == {"detail": "internal server error"}
    assert "Traceback" not in response.text and "/secret/path" not in response.text
    assert client.get("/sessions/s-500/messages").status_code == 404
