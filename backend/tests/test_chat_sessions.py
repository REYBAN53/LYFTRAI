"""Successful chat, multi-turn context, session isolation, history endpoint and SQLite persistence."""

from __future__ import annotations

import sqlite3

from fastapi.testclient import TestClient

from app.config import DEFAULT_SYSTEM_PROMPT
from app.main import create_app
from tests.conftest import FAKE_MODEL, TEST_KEYS


def test_first_chat_returns_full_contract(chat, provider) -> None:  # type: ignore[no-untyped-def]
    response = chat("s-7f3a", "What is the capital of France?")
    assert response.status_code == 200
    body = response.json()
    assert body["session_id"] == "s-7f3a"
    assert body["reply"] == "Reply #1 to: What is the capital of France?"
    meta = body["metadata"]
    assert meta["resolution_source"] == "LIVE_INFERENCE"
    assert meta["model"] == FAKE_MODEL
    assert isinstance(meta["latency_ms"], int) and meta["latency_ms"] > 0
    assert meta["key_id"] == "key_1"
    assert meta["fallback_attempts"] == 0
    assert provider.calls[0].api_key == TEST_KEYS[0]


def test_token_usage_is_per_request_and_matches_provider(chat, provider) -> None:  # type: ignore[no-untyped-def]
    first = chat("s-tok", "one two three").json()["metadata"]
    sent = provider.calls[-1].messages
    assert first["input_tokens"] == sum(len(m["content"].split()) + 4 for m in sent)
    assert first["output_tokens"] == len("Reply #1 to: one two three".split())

    second = chat("s-tok", "four").json()["metadata"]
    sent = provider.calls[-1].messages
    # Second turn's input covers system + history + new message, never a running total of outputs.
    assert second["input_tokens"] == sum(len(m["content"].split()) + 4 for m in sent)
    assert second["output_tokens"] == len("Reply #2 to: four".split())


def test_equal_length_first_messages_report_same_input_tokens(chat) -> None:  # type: ignore[no-untyped-def]
    a = chat("s-a", "alpha beta").json()["metadata"]
    b = chat("s-b", "gamma delta").json()["metadata"]
    assert a["input_tokens"] == b["input_tokens"]


def test_multi_turn_sends_full_history_with_system_prompt(chat, provider) -> None:  # type: ignore[no-untyped-def]
    chat("s-mt", "My name is Ada.")
    chat("s-mt", "I like chess.")
    chat("s-mt", "What is my name?")
    sent = provider.calls[-1].messages
    assert sent == [
        {"role": "system", "content": DEFAULT_SYSTEM_PROMPT},
        {"role": "user", "content": "My name is Ada."},
        {"role": "assistant", "content": "Reply #1 to: My name is Ada."},
        {"role": "user", "content": "I like chess."},
        {"role": "assistant", "content": "Reply #2 to: I like chess."},
        {"role": "user", "content": "What is my name?"},
    ]


def test_sessions_are_isolated(chat, provider) -> None:  # type: ignore[no-untyped-def]
    chat("s-one", "Secret for session one")
    chat("s-two", "Hello from session two")
    chat("s-two", "Second message in two")
    sent = provider.calls[-1].messages
    assert all("Secret for session one" not in m["content"] for m in sent)
    assert [m["content"] for m in sent if m["role"] == "user"] == ["Hello from session two", "Second message in two"]


def test_history_endpoint_oldest_first_with_assistant_metadata(client: TestClient, chat) -> None:  # type: ignore[no-untyped-def]
    r1 = chat("s-hist", "first").json()
    chat("s-hist", "second")
    body = client.get("/sessions/s-hist/messages").json()
    assert body["session_id"] == "s-hist"
    messages = body["messages"]
    assert [(m["role"], m["content"]) for m in messages] == [
        ("user", "first"),
        ("assistant", "Reply #1 to: first"),
        ("user", "second"),
        ("assistant", "Reply #2 to: second"),
    ]
    assert "metadata" not in messages[0] or messages[0]["metadata"] is None
    assert messages[1]["metadata"] == r1["metadata"]
    assert all(m["role"] != "system" for m in messages)


def test_custom_system_prompt_applies_to_session_but_not_history(client: TestClient, chat, provider) -> None:  # type: ignore[no-untyped-def]
    chat("s-sys", "hi", system_prompt="You are a pirate.")
    assert provider.calls[-1].messages[0] == {"role": "system", "content": "You are a pirate."}
    chat("s-sys", "again")  # no system_prompt sent: the session keeps its override
    assert provider.calls[-1].messages[0] == {"role": "system", "content": "You are a pirate."}
    history = client.get("/sessions/s-sys/messages").json()["messages"]
    assert all("pirate" not in m["content"] for m in history)
    chat("s-other", "hi")  # other sessions are unaffected
    assert provider.calls[-1].messages[0]["content"] == DEFAULT_SYSTEM_PROMPT


def test_history_is_persisted_in_sqlite_and_survives_restart(settings, provider) -> None:  # type: ignore[no-untyped-def]
    with TestClient(create_app(settings)) as first_app:
        assert first_app.post("/chat", json={"session_id": "s-persist", "message": "remember me"}).status_code == 200

    db_path = settings.database_url.removeprefix("sqlite:///")
    with sqlite3.connect(db_path) as connection:
        rows = connection.execute(
            "SELECT role, content, metadata IS NOT NULL, created_at FROM messages WHERE session_id = ? ORDER BY id",
            ("s-persist",),
        ).fetchall()
    assert [(r[0], r[1], bool(r[2])) for r in rows] == [
        ("user", "remember me", False),
        ("assistant", "Reply #1 to: remember me", True),
    ]
    assert all(r[3].endswith("Z") and "T" in r[3] for r in rows)  # ISO-8601 server time

    with TestClient(create_app(settings)) as restarted_app:  # new process state, same database file
        history = restarted_app.get("/sessions/s-persist/messages").json()["messages"]
        assert [m["content"] for m in history] == ["remember me", "Reply #1 to: remember me"]
        restarted_app.post("/chat", json={"session_id": "s-persist", "message": "and now?"})
    assert [m["role"] for m in provider.calls[-1].messages] == ["system", "user", "assistant", "user"]
