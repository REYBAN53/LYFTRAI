"""Key failover: real provider errors and the X-Simulate-Failure test hook."""

from __future__ import annotations

import logging

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from tests.conftest import TEST_KEYS, make_settings

ALL_DOWN = {"detail": "all providers unavailable"}


# --- Real provider errors (raised by the fake provider through LiteLLM) ----------------------


@pytest.mark.parametrize("status", [429, 500, 503])
def test_first_key_error_fails_over_to_second_key(chat, provider, status) -> None:  # type: ignore[no-untyped-def]
    provider.failing_keys[TEST_KEYS[0]] = status
    body = chat("s-real", "hello").json()
    assert body["metadata"]["key_id"] == "key_2"
    assert body["metadata"]["fallback_attempts"] == 1
    assert body["metadata"]["resolution_source"] == "LIVE_INFERENCE"
    assert body["reply"] == "Reply #1 to: hello"


def test_all_keys_failing_returns_503_and_persists_nothing(client: TestClient, chat, provider) -> None:  # type: ignore[no-untyped-def]
    provider.failing_keys.update({TEST_KEYS[0]: 429, TEST_KEYS[1]: 500})
    response = chat("s-down", "hello")
    assert response.status_code == 503
    assert response.json() == ALL_DOWN
    assert client.get("/sessions/s-down/messages").status_code == 404


def test_failed_turn_does_not_corrupt_existing_history(client: TestClient, chat, provider) -> None:  # type: ignore[no-untyped-def]
    chat("s-keep", "first")
    provider.failing_keys.update({TEST_KEYS[0]: 503, TEST_KEYS[1]: 503})
    assert chat("s-keep", "this one fails").status_code == 503
    provider.failing_keys.clear()
    chat("s-keep", "third")
    contents = [m["content"] for m in client.get("/sessions/s-keep/messages").json()["messages"]]
    assert contents == ["first", "Reply #1 to: first", "third", "Reply #2 to: third"]
    assert "this one fails" not in [m["content"] for m in provider.calls[-1].messages]


def test_api_keys_never_leak_into_responses_or_logs(chat, provider, caplog) -> None:  # type: ignore[no-untyped-def]
    provider.failing_keys.update({TEST_KEYS[0]: 429, TEST_KEYS[1]: 500})
    with caplog.at_level(logging.DEBUG):
        response = chat("s-leak", "hello")
    for secret in TEST_KEYS:
        assert secret not in response.text
        assert secret not in caplog.text


# --- X-Simulate-Failure ----------------------------------------------------------------------


@pytest.mark.parametrize("header", ["key_1=429", "key_1=500", "key_1=502", "key_1=503"])
def test_simulated_first_key_failure_fails_over(chat, provider, header) -> None:  # type: ignore[no-untyped-def]
    response = chat("s-sim", "What is 2+2?", headers={"X-Simulate-Failure": header})
    assert response.status_code == 200
    meta = response.json()["metadata"]
    assert meta["key_id"] == "key_2"
    assert meta["fallback_attempts"] == 1
    assert meta["resolution_source"] == "LIVE_INFERENCE"
    assert response.json()["reply"] == "Reply #1 to: What is 2+2?"  # a real answer, not an error in a 200
    assert provider.live_calls_for(0) == 0  # simulated failure never touched the real key_1
    assert provider.live_calls_for(1) == 1


@pytest.mark.parametrize("header", ["*=429", "key_1=429,key_2=500", "key_2=503, *=502"])
def test_simulated_total_outage_returns_503_and_persists_nothing(client: TestClient, chat, provider, header) -> None:  # type: ignore[no-untyped-def]
    response = chat("s-sim-down", "hello", headers={"X-Simulate-Failure": header})
    assert response.status_code == 503
    assert response.json() == ALL_DOWN
    assert provider.calls == []
    assert client.get("/sessions/s-sim-down/messages").status_code == 404


def test_simulation_affects_only_that_request(chat, provider) -> None:  # type: ignore[no-untyped-def]
    assert chat("s-once", "a", headers={"X-Simulate-Failure": "*=429"}).status_code == 503
    after = chat("s-once", "b").json()["metadata"]
    assert after["key_id"] == "key_1" and after["fallback_attempts"] == 0


def test_simulation_bypasses_cache_so_failover_is_always_demonstrable(chat, provider) -> None:  # type: ignore[no-untyped-def]
    chat("s-cache-1", "same question")
    response = chat("s-cache-2", "same question", headers={"X-Simulate-Failure": "key_1=429"})
    meta = response.json()["metadata"]
    assert meta["resolution_source"] == "LIVE_INFERENCE"
    assert meta["key_id"] == "key_2"
    outage = chat("s-cache-3", "same question", headers={"X-Simulate-Failure": "*=429"})
    assert outage.status_code == 503


def test_simulation_with_three_keys_counts_every_failed_key(tmp_path, provider) -> None:  # type: ignore[no-untyped-def]
    settings = make_settings(tmp_path, llm_api_keys="k-one,k-two,k-three")
    with TestClient(create_app(settings)) as client:
        response = client.post(
            "/chat",
            json={"session_id": "s3", "message": "hi"},
            headers={"X-Simulate-Failure": "key_1=429,key_2=500"},
        )
    meta = response.json()["metadata"]
    assert meta["key_id"] == "key_3"
    assert meta["fallback_attempts"] == 2


def test_simulation_combines_with_real_failures(chat, provider) -> None:  # type: ignore[no-untyped-def]
    provider.failing_keys[TEST_KEYS[1]] = 429  # key_2 is genuinely rate limited
    response = chat("s-mix", "hi", headers={"X-Simulate-Failure": "key_1=500"})
    assert response.status_code == 503


def test_header_is_ignored_when_simulation_is_disabled(tmp_path, provider) -> None:  # type: ignore[no-untyped-def]
    settings = make_settings(tmp_path, enable_failure_simulation=False)
    with TestClient(create_app(settings)) as client:
        response = client.post(
            "/chat", json={"session_id": "s-off", "message": "hi"}, headers={"X-Simulate-Failure": "*=429"}
        )
    assert response.status_code == 200
    assert response.json()["metadata"]["key_id"] == "key_1"
    assert response.json()["metadata"]["fallback_attempts"] == 0


@pytest.mark.parametrize("header", ["key_1=404", "key_1", "banana=429", "key_0=429", "key_1=abc"])
def test_malformed_simulation_header_is_rejected_with_422(client: TestClient, chat, provider, header) -> None:  # type: ignore[no-untyped-def]
    response = chat("s-bad-header", "hi", headers={"X-Simulate-Failure": header})
    assert response.status_code == 422
    assert "X-Simulate-Failure" in response.json()["detail"]
    assert provider.calls == []
    assert client.get("/sessions/s-bad-header/messages").status_code == 404
