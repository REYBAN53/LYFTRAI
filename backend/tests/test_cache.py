"""LiteLLM response cache behaviour (real LiteLLM cache; only the provider is faked)."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_same_first_message_in_new_session_is_served_from_cache(chat, provider) -> None:  # type: ignore[no-untyped-def]
    live = chat("s-c1", "What is the capital of France?").json()
    cached = chat("s-c2", "What is the capital of France?").json()

    assert live["metadata"]["resolution_source"] == "LIVE_INFERENCE"
    assert cached["metadata"]["resolution_source"] == "LLM_CACHE"
    assert cached["reply"] == live["reply"]
    assert cached["metadata"]["input_tokens"] == live["metadata"]["input_tokens"]
    assert cached["metadata"]["output_tokens"] == live["metadata"]["output_tokens"]
    assert cached["metadata"]["key_id"] is None
    assert cached["metadata"]["fallback_attempts"] == 0
    assert cached["metadata"]["model"] == live["metadata"]["model"]
    assert cached["metadata"]["latency_ms"] < live["metadata"]["latency_ms"]
    assert len(provider.calls) == 1  # the second request never reached the provider


def test_cache_hit_is_persisted_to_the_new_session(client: TestClient, chat) -> None:  # type: ignore[no-untyped-def]
    chat("s-p1", "hello")
    chat("s-p2", "hello")
    history = client.get("/sessions/s-p2/messages").json()["messages"]
    assert history[1]["metadata"]["resolution_source"] == "LLM_CACHE"


def test_different_message_is_never_served_from_cache(chat, provider) -> None:  # type: ignore[no-untyped-def]
    chat("s-d1", "What is the capital of France?")
    other = chat("s-d2", "What is the capital of Spain?").json()
    assert other["metadata"]["resolution_source"] == "LIVE_INFERENCE"
    assert other["reply"].endswith("Spain?")
    assert len(provider.calls) == 2


def test_cache_key_includes_history(chat, provider) -> None:  # type: ignore[no-untyped-def]
    chat("s-h1", "Hi")
    chat("s-h1", "Tell me more")
    chat("s-h2", "Different opener")
    follow_up = chat("s-h2", "Tell me more").json()  # same text, different history -> different key
    assert follow_up["metadata"]["resolution_source"] == "LIVE_INFERENCE"


def test_cache_key_includes_system_prompt(chat) -> None:  # type: ignore[no-untyped-def]
    chat("s-sp1", "Hello", system_prompt="Be formal.")
    other = chat("s-sp2", "Hello", system_prompt="Be casual.").json()
    assert other["metadata"]["resolution_source"] == "LIVE_INFERENCE"


def test_long_multi_turn_conversations_are_cacheable(chat, provider) -> None:  # type: ignore[no-untyped-def]
    # LiteLLM skips caching above 4 messages by default; we disable that limit deliberately.
    turns = ["one", "two", "three", "four"]
    for turn in turns:
        chat("s-long-a", turn)
    calls_before = len(provider.calls)
    results = [chat("s-long-b", turn).json() for turn in turns]
    assert [r["metadata"]["resolution_source"] for r in results] == ["LLM_CACHE"] * 4
    assert len(provider.calls) == calls_before


def test_cache_hit_reports_cache_even_when_first_key_is_down(chat, provider) -> None:  # type: ignore[no-untyped-def]
    from tests.conftest import TEST_KEYS

    chat("s-k1", "cached question")
    provider.failing_keys[TEST_KEYS[0]] = 429
    cached = chat("s-k2", "cached question").json()["metadata"]
    assert cached["resolution_source"] == "LLM_CACHE"
    assert cached["key_id"] is None and cached["fallback_attempts"] == 0
