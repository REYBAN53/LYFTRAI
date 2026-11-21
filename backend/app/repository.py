"""Data-access layer for chat sessions. All SQL lives here; callers never touch the ORM directly."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.db import ChatSession, Message, utc_now_iso


@dataclass(frozen=True)
class StoredMessage:
    role: str
    content: str
    metadata: dict[str, Any] | None
    created_at: str


@dataclass(frozen=True)
class SessionContext:
    """Everything needed to build the next LLM request for a session."""

    exists: bool
    system_prompt: str | None
    history: list[StoredMessage]


class ChatRepository:
    def __init__(self, session_factory: sessionmaker) -> None:
        self._session_factory = session_factory

    def load_context(self, session_id: str) -> SessionContext:
        with self._session_factory() as db:
            chat = db.get(ChatSession, session_id)
            if chat is None:
                return SessionContext(exists=False, system_prompt=None, history=[])
            return SessionContext(
                exists=True, system_prompt=chat.system_prompt, history=self._history(db, session_id)
            )

    def get_history(self, session_id: str) -> list[StoredMessage] | None:
        """Oldest-first history, or None if the session does not exist."""
        with self._session_factory() as db:
            if db.get(ChatSession, session_id) is None:
                return None
            return self._history(db, session_id)

    def save_turn(
        self,
        *,
        session_id: str,
        system_prompt_override: str | None,
        user_content: str,
        assistant_content: str,
        assistant_metadata: dict[str, Any],
    ) -> None:
        """Persist a successful exchange atomically: both messages are written, or neither is."""
        now = utc_now_iso()
        with self._session_factory.begin() as db:
            chat = db.get(ChatSession, session_id)
            if chat is None:
                chat = ChatSession(id=session_id, created_at=now, updated_at=now)
                db.add(chat)
            chat.updated_at = now
            if system_prompt_override is not None:
                chat.system_prompt = system_prompt_override
            db.add(Message(session_id=session_id, role="user", content=user_content, created_at=now))
            db.add(
                Message(
                    session_id=session_id,
                    role="assistant",
                    content=assistant_content,
                    metadata_json=json.dumps(assistant_metadata),
                    created_at=utc_now_iso(),
                )
            )

    @staticmethod
    def _history(db: Session, session_id: str) -> list[StoredMessage]:
        rows = db.scalars(
            select(Message).where(Message.session_id == session_id).order_by(Message.id.asc())
        )
        return [
            StoredMessage(
                role=row.role,
                content=row.content,
                metadata=json.loads(row.metadata_json) if row.metadata_json else None,
                created_at=row.created_at,
            )
            for row in rows
        ]
