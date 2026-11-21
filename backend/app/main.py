"""Application factory: wiring, middleware and error handling."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes import router
from app.chat_service import ChatService
from app.config import Settings
from app.db import create_db_engine, init_schema, make_session_factory
from app.llm.gateway import LLMGateway, configure_litellm
from app.llm.keys import KeyPool
from app.llm.simulation import SIMULATION_HEADER
from app.repository import ChatRepository

logger = logging.getLogger("app")


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    logging.basicConfig(
        level=settings.log_level.upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        engine = create_db_engine(settings.database_url)
        init_schema(engine)
        configure_litellm(settings)
        key_pool = KeyPool(settings.api_keys)
        gateway = LLMGateway(
            key_pool=key_pool,
            model=settings.llm_model,
            timeout_seconds=settings.llm_timeout_seconds,
            max_tokens=settings.llm_max_tokens,
        )
        app.state.settings = settings
        app.state.engine = engine
        app.state.gateway = gateway
        app.state.chat_service = ChatService(
            repository=ChatRepository(make_session_factory(engine)),
            gateway=gateway,
            default_system_prompt=settings.default_system_prompt,
        )
        if len(key_pool) < 2:
            logger.warning("LLM_API_KEYS has %d key(s); configure at least 2 for failover", len(key_pool))
        logger.info(
            "started: model=%s keys=%d cache_ttl=%ss simulation=%s",
            settings.llm_model,
            len(key_pool),
            settings.llm_cache_ttl_seconds,
            settings.enable_failure_simulation,
        )
        yield
        engine.dispose()

    app = FastAPI(
        title="Lyftr Chat API",
        version="1.0.0",
        description="LLM chatbot backend with key failover and LiteLLM response caching.",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Content-Type", SIMULATION_HEADER],
        max_age=600,
    )

    @app.exception_handler(Exception)
    async def unhandled_exception(_request: Request, exc: Exception) -> JSONResponse:
        # Never leak a stack trace or HTML error page to clients; log it server-side instead.
        logger.error("unhandled error: %s", type(exc).__name__, exc_info=exc)
        return JSONResponse(status_code=500, content={"detail": "internal server error"})

    app.include_router(router)
    return app
