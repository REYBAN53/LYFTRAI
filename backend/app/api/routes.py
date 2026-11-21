"""HTTP layer: the three endpoints of the contract. Business logic lives in ChatService."""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Header, HTTPException, Path, Request
from fastapi.responses import JSONResponse

from app.chat_service import ChatService, SessionNotFound
from app.db import ping
from app.llm.gateway import AllProvidersUnavailable, cache_enabled
from app.llm.simulation import SIMULATION_HEADER, FailurePlan, InvalidSimulationHeader, parse_failure_header
from app.schemas import MAX_SESSION_ID_CHARS, ChatRequest, ChatResponse, HealthResponse, HistoryResponse

logger = logging.getLogger(__name__)
router = APIRouter()


def _service(request: Request) -> ChatService:
    return request.app.state.chat_service


@router.get("/health", response_model=HealthResponse)
def health(request: Request) -> HealthResponse | JSONResponse:
    state = request.app.state
    try:
        ping(state.engine)
    except Exception:
        logger.exception("health check: database unreachable")
        return JSONResponse(status_code=503, content={"status": "unavailable", "detail": "database unreachable"})
    if state.gateway.keys_configured == 0:
        return JSONResponse(
            status_code=503, content={"status": "unavailable", "detail": "no LLM API keys configured"}
        )
    return HealthResponse(
        status="ok",
        keys_configured=state.gateway.keys_configured,
        cache_enabled=cache_enabled(),
        model=state.gateway.model,
        failure_simulation_enabled=state.settings.enable_failure_simulation,
    )


@router.post("/chat", response_model=ChatResponse)
async def chat(
    body: ChatRequest,
    request: Request,
    x_simulate_failure: Annotated[str | None, Header(alias=SIMULATION_HEADER)] = None,
) -> ChatResponse:
    failure_plan = _failure_plan(request, x_simulate_failure)
    try:
        return await _service(request).chat(body, failure_plan)
    except AllProvidersUnavailable:
        raise HTTPException(status_code=503, detail="all providers unavailable") from None


@router.get("/sessions/{session_id}/messages", response_model=HistoryResponse)
async def session_messages(
    request: Request,
    session_id: Annotated[str, Path(min_length=1, max_length=MAX_SESSION_ID_CHARS)],
) -> HistoryResponse:
    try:
        return await _service(request).history(session_id)
    except SessionNotFound:
        raise HTTPException(status_code=404, detail="session not found") from None


def _failure_plan(request: Request, header_value: str | None) -> FailurePlan | None:
    if header_value is None:
        return None
    if not request.app.state.settings.enable_failure_simulation:
        logger.info("%s header ignored: ENABLE_FAILURE_SIMULATION is off", SIMULATION_HEADER)
        return None
    try:
        return parse_failure_header(header_value)
    except InvalidSimulationHeader as exc:
        raise HTTPException(status_code=422, detail=f"invalid {SIMULATION_HEADER} header: {exc}") from None
