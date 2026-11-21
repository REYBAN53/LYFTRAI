"""Unit tests for the key pool and the failure-simulation parser."""

from __future__ import annotations

import pytest

from app.config import Settings
from app.llm.keys import KeyPool
from app.llm.simulation import InvalidSimulationHeader, parse_failure_header


def test_key_ids_follow_configuration_order() -> None:
    settings = Settings(_env_file=None, llm_api_keys=" first , second,,third ")
    pool = KeyPool(settings.api_keys)
    assert [key.key_id for key in pool] == ["key_1", "key_2", "key_3"]
    assert [key.secret for key in pool] == ["first", "second", "third"]


def test_key_secret_is_hidden_from_repr_and_redacted() -> None:
    pool = KeyPool(["super-secret-value"])
    key = next(iter(pool))
    assert "super-secret-value" not in repr(key)
    assert pool.redact("error for super-secret-value") == "error for <key_1>"


def test_parse_specific_keys_and_wildcard() -> None:
    plan = parse_failure_header("key_1=429, key_2=500")
    assert plan.status_for("key_1") == 429
    assert plan.status_for("key_2") == 500
    assert plan.status_for("key_3") is None

    plan = parse_failure_header("*=503,key_2=429")
    assert plan.status_for("key_1") == 503
    assert plan.status_for("key_2") == 429  # explicit entry beats the wildcard


def test_empty_header_is_inactive() -> None:
    assert not parse_failure_header("").is_active
    assert not parse_failure_header(" , ").is_active


@pytest.mark.parametrize("raw", ["key_1=418", "key_1", "=429", "key1=429", "key_1=", "*=abc"])
def test_invalid_headers_raise(raw: str) -> None:
    with pytest.raises(InvalidSimulationHeader):
        parse_failure_header(raw)


def test_cors_origins_parse() -> None:
    settings = Settings(_env_file=None, allowed_origins="http://a.com, https://b.app ,")
    assert settings.cors_origins == ["http://a.com", "https://b.app"]


def test_redact_also_removes_key_like_tokens_not_in_pool() -> None:
    pool = KeyPool(["mine"])
    text = pool.redact("GET https://x/v1?key=AIzaSyFAKEFAKEFAKEFAKEFAKEFAKE12&alt=sse failed for mine")
    assert "AIza" not in text and "mine" not in text
    assert "key=<redacted>&alt=sse" in text
