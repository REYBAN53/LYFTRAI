"""Chat orchestration: load session context, call the LLM gateway, persist the turn."""

from __future__ import annotations

import asyncio
import logging
import time
import weakref

from starlette.concurrency import run_in_threadpool

from app.llm.gateway import ChatMessages, LLMGateway
from app.llm.simulation import FailurePlan
from app.repository import ChatRepository, SessionContext
from app.schemas import ChatMetadata, ChatRequest, ChatResponse, HistoryMessage, HistoryResponse

logger = logging.getLogger(__name__)


class SessionNotFound(Exception):
    pass


class ChatService:
    def __init__(self, *, repository: ChatRepository, gateway: LLMGateway, default_system_prompt: str) -> None:
        self._repository = repository
        self._gateway = gateway
        self._default_system_prompt = default_system_prompt
        # One lock per active session so two concurrent turns in the same session cannot interleave
        # their history. Entries disappear automatically once no request holds them.
        self._session_locks: weakref.WeakValueDictionary[str, asyncio.Lock] = weakref.WeakValueDictionary()

    async def chat(self, request: ChatRequest, failure_plan: FailurePlan | None = None) -> ChatResponse:
        started = time.perf_counter()
        lock = self._session_locks.setdefault(request.session_id, asyncio.Lock())
        async with lock:
            context = await run_in_threadpool(self._repository.load_context, request.session_id)
            system_prompt = request.system_prompt or context.system_prompt or self._default_system_prompt
            messages = self._build_messages(system_prompt, context, request.message)

            # Raises AllProvidersUnavailable before anything is written: failed turns never persist.
            completion = await self._gateway.complete(messages, failure_plan)

            metadata = ChatMetadata(
                resolution_source="LLM_CACHE" if completion.cache_hit else "LIVE_INFERENCE",
                model=completion.model,
                # Server-side time to resolve the reply (history load + cache lookup / inference).
                latency_ms=round((time.perf_counter() - started) * 1000),
                input_tokens=completion.input_tokens,
                output_tokens=completion.output_tokens,
                key_id=completion.key_id,
                fallback_attempts=completion.fallback_attempts,
            )
            await run_in_threadpool(
                self._repository.save_turn,
                session_id=request.session_id,
                system_prompt_override=request.system_prompt,
                user_content=request.message,
                assistant_content=completion.reply,
                assistant_metadata=metadata.model_dump(),
            )

        logger.info(
            "chat session=%s source=%s key=%s fallbacks=%d tokens=%d/%d latency=%dms",
            request.session_id,
            metadata.resolution_source,
            metadata.key_id,
            metadata.fallback_attempts,
            metadata.input_tokens,
            metadata.output_tokens,
            metadata.latency_ms,
        )
        return ChatResponse(session_id=request.session_id, reply=completion.reply, metadata=metadata)

    async def history(self, session_id: str) -> HistoryResponse:
        stored = await run_in_threadpool(self._repository.get_history, session_id)
        if stored is None:
            raise SessionNotFound(session_id)
        return HistoryResponse(
            session_id=session_id,
            messages=[
                HistoryMessage(role=m.role, content=m.content, metadata=m.metadata, created_at=m.created_at)  # type: ignore[arg-type]
                for m in stored
            ],
        )

    @staticmethod
    def _build_messages(system_prompt: str, context: SessionContext, new_message: str) -> ChatMessages:
        """The full list sent to the LLM (and therefore the cache key): system + history + new message."""
        return [
            {"role": "system", "content": system_prompt},
            *({"role": m.role, "content": m.content} for m in context.history),
            {"role": "user", "content": new_message},
        ]
