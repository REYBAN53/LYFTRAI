"""Test fixtures.

External LLM calls are replaced by a LiteLLM *custom provider* (``fakellm/...``) rather than by
patching ``litellm.acompletion``. Every request still flows through the real LiteLLM pipeline,
including its built-in response cache, so cache behaviour is tested for real; only the network
hop to a model vendor is simulated.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from pathlib import Path

import litellm
import pytest
from fastapi.testclient import TestClient
from litellm.llms.custom_llm import CustomLLM

from app.config import Settings
from app.main import create_app

FAKE_MODEL = "fakellm/test-model"
TEST_KEYS = ["sk-test-secret-one", "sk-test-secret-two"]
LIVE_DELAY_SECONDS = 0.15

_ERRORS: dict[int, Callable[[], Exception]] = {
    429: lambda: litellm.RateLimitError(message="quota exceeded", llm_provider="fakellm", model=FAKE_MODEL),
    500: lambda: litellm.InternalServerError(message="boom", llm_provider="fakellm", model=FAKE_MODEL),
    503: lambda: litellm.ServiceUnavailableError(message="overloaded", llm_provider="fakellm", model=FAKE_MODEL),
}


@dataclass
class ProviderCall:
    api_key: str
    messages: list[dict[str, str]]


@dataclass
class FakeProvider(CustomLLM):
    """Deterministic stand-in for a model vendor. Behaviour is controlled per API key."""

    calls: list[ProviderCall] = field(default_factory=list)
    failing_keys: dict[str, int] = field(default_factory=dict)  # api_key -> HTTP status to raise

    def __post_init__(self) -> None:
        super().__init__()

    async def acompletion(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        api_key, messages = kwargs["api_key"], kwargs["messages"]
        self.calls.append(ProviderCall(api_key=api_key, messages=[dict(m) for m in messages]))
        if api_key in self.failing_keys:
            raise _ERRORS[self.failing_keys[api_key]]()
        await asyncio.sleep(LIVE_DELAY_SECONDS)
        last = messages[-1]["content"]
        reply = f"Reply #{sum(m['role'] == 'user' for m in messages)} to: {last}"
        prompt_tokens = sum(len(m["content"].split()) + 4 for m in messages)
        completion_tokens = len(reply.split())
        return litellm.ModelResponse(
            model="test-model",
            choices=[{"message": {"role": "assistant", "content": reply}, "finish_reason": "stop"}],
            usage={
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": prompt_tokens + completion_tokens,
            },
        )

    def live_calls_for(self, key_index: int) -> int:
        return sum(call.api_key == TEST_KEYS[key_index] for call in self.calls)


@pytest.fixture
def provider() -> Iterator[FakeProvider]:
    fake = FakeProvider()
    previous = litellm.custom_provider_map
    litellm.custom_provider_map = [{"provider": "fakellm", "custom_handler": fake}]
    litellm.utils.custom_llm_setup()
    yield fake
    litellm.custom_provider_map = previous


def make_settings(tmp_path: Path, **overrides) -> Settings:  # type: ignore[no-untyped-def]
    values = {
        "llm_api_keys": ",".join(TEST_KEYS),
        "llm_model": FAKE_MODEL,
        "database_url": f"sqlite:///{tmp_path / 'app.db'}",
        "allowed_origins": "http://localhost:3000",
        "enable_failure_simulation": True,
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return make_settings(tmp_path)


@pytest.fixture
def client(settings: Settings, provider: FakeProvider) -> Iterator[TestClient]:
    with TestClient(create_app(settings)) as test_client:
        yield test_client


@pytest.fixture
def chat(client: TestClient) -> Callable[..., object]:
    def _chat(session_id: str, message: str, headers: dict[str, str] | None = None, **extra):  # type: ignore[no-untyped-def]
        return client.post("/chat", json={"session_id": session_id, "message": message, **extra}, headers=headers or {})

    return _chat
