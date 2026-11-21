"""LLM gateway: ordered key failover on top of LiteLLM, with LiteLLM's built-in response cache.

Request lifecycle for one chat turn::

    for key in pool (key_1, key_2, ...):
        if X-Simulate-Failure says this key fails -> record failure, try next key (no network call)
        litellm.acompletion(model, messages, api_key=key)
            -> LiteLLM checks its cache first (key = model + messages + params, NOT the api key)
               hit  -> return cached response (usage preserved)    => LLM_CACHE, key_id=None
               miss -> call provider with this key, write to cache => LIVE_INFERENCE, key_id=key
        on 429 / quota / 5xx / timeout / connection / auth error -> record failure, try next key
    all keys failed -> AllProvidersUnavailable (HTTP 503)

Why failover is an explicit loop rather than litellm.Router: the contract needs to report exactly
which key answered and how many keys failed first, and to inject per-key failures for a single
request. Router's deployment cooldowns would also turn a *simulated* failure into real
shared state that affects later requests. A small ordered loop keeps all of that deterministic.
"""

from __future__ import annotations

import importlib
import logging
from dataclasses import dataclass
from typing import Any

import litellm
from litellm.caching.caching import Cache

from app.config import Settings
from app.llm.keys import KeyPool
from app.llm.simulation import FailurePlan

logger = logging.getLogger(__name__)

ChatMessages = list[dict[str, str]]


@dataclass(frozen=True)
class FailedAttempt:
    key_id: str
    status_code: int | None
    reason: str
    simulated: bool


@dataclass(frozen=True)
class Completion:
    reply: str
    model: str
    input_tokens: int
    output_tokens: int
    cache_hit: bool
    key_id: str | None
    fallback_attempts: int


class AllProvidersUnavailable(Exception):
    def __init__(self, attempts: list[FailedAttempt]) -> None:
        super().__init__("all providers unavailable")
        self.attempts = attempts


class EmptyCompletion(Exception):
    """The provider answered but produced no text (e.g. blocked by a safety filter)."""


def configure_litellm(settings: Settings) -> None:
    """Global LiteLLM setup: quiet logging and the built-in response cache."""
    litellm.suppress_debug_info = True
    litellm.telemetry = False
    logging.getLogger("LiteLLM").setLevel(logging.WARNING)

    litellm.cache = Cache(
        type="local",  # LiteLLM's in-memory cache; no external service (no Redis)
        ttl=settings.llm_cache_ttl_seconds,
        # LiteLLM skips caching for requests with more than 4 messages by default. The contract
        # keys the cache on the full message list, so multi-turn requests must be cacheable too.
        max_messages=None,
    )

    # LiteLLM imports its cache-hit handling lazily (~150 ms on first use). Import it now so the
    # first cache hit after startup is not slowed down by a module import.
    try:
        importlib.import_module("litellm.llms.anthropic.messages.native.response_cache")
    except ImportError:  # pragma: no cover - internal module path may move between versions
        logger.debug("LiteLLM cache warm-up import skipped")


def cache_enabled() -> bool:
    return litellm.cache is not None


class LLMGateway:
    def __init__(self, *, key_pool: KeyPool, model: str, timeout_seconds: float, max_tokens: int) -> None:
        self._keys = key_pool
        self._model = model
        self._timeout = timeout_seconds
        self._max_tokens = max_tokens

    @property
    def model(self) -> str:
        return self._model

    @property
    def keys_configured(self) -> int:
        return len(self._keys)

    async def complete(self, messages: ChatMessages, failure_plan: FailurePlan | None = None) -> Completion:
        failures: list[FailedAttempt] = []
        simulating = failure_plan is not None and failure_plan.is_active

        for key in self._keys:
            simulated_status = failure_plan.status_for(key.key_id) if failure_plan else None
            if simulated_status is not None:
                failures.append(FailedAttempt(key.key_id, simulated_status, "simulated failure", simulated=True))
                logger.warning("key %s failed (simulated HTTP %s); failing over", key.key_id, simulated_status)
                continue

            request: dict[str, Any] = {
                "model": self._model,
                "messages": messages,
                "api_key": key.secret,
                "max_tokens": self._max_tokens,
                "timeout": self._timeout,
                "num_retries": 0,  # failover across keys is handled here, not by in-key retries
            }
            if simulating:
                # A failover demo must exercise real keys: skip the cache *read* so a previously
                # cached answer cannot mask the simulated outage. The result is still cached.
                request["cache"] = {"no-cache": True}

            try:
                response = await litellm.acompletion(**request)
                reply = _extract_reply(response)
            except Exception as exc:  # provider boundary: every failure means "try the next key"
                status = getattr(exc, "status_code", None)
                reason = self._keys.redact(f"{type(exc).__name__}: {exc}")[:300]
                failures.append(FailedAttempt(key.key_id, status, reason, simulated=False))
                logger.warning("key %s failed (HTTP %s, %s); failing over", key.key_id, status, type(exc).__name__)
                continue

            cache_hit = bool((getattr(response, "_hidden_params", None) or {}).get("cache_hit"))
            input_tokens, output_tokens = _usage(response, messages, reply, self._model)
            return Completion(
                reply=reply,
                model=self._model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cache_hit=cache_hit,
                key_id=None if cache_hit else key.key_id,
                fallback_attempts=0 if cache_hit else len(failures),
            )

        logger.error(
            "all %d keys failed: %s",
            len(self._keys),
            ", ".join(f"{f.key_id}={f.status_code}{' (simulated)' if f.simulated else ''}" for f in failures),
        )
        raise AllProvidersUnavailable(failures)


def _extract_reply(response: Any) -> str:
    try:
        content = response.choices[0].message.content
    except (AttributeError, IndexError) as exc:
        raise EmptyCompletion("response had no choices") from exc
    if not isinstance(content, str) or not content.strip():
        raise EmptyCompletion("response had no text content")
    return content


def _usage(response: Any, messages: ChatMessages, reply: str, model: str) -> tuple[int, int]:
    """Provider-reported usage for this request. Cached responses carry the usage stored with them."""
    usage = getattr(response, "usage", None)
    prompt = getattr(usage, "prompt_tokens", None)
    completion = getattr(usage, "completion_tokens", None)
    if isinstance(prompt, int) and isinstance(completion, int):
        return prompt, completion
    # Rare: provider omitted usage. Fall back to LiteLLM's tokenizer-based count.
    logger.warning("provider returned no usage data; estimating with litellm.token_counter")
    return (
        litellm.token_counter(model=model, messages=messages),
        litellm.token_counter(model=model, text=reply),
    )
