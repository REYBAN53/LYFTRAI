"""The API key pool. Keys are addressed by stable ids (key_1, key_2, ...) and never exposed."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# Anything that looks like a credential even if it is not one of ours (e.g. echoed in a URL).
_KEY_LIKE = re.compile(r"(AIza[0-9A-Za-z_\-]{20,}|(?<=key=)[^&\s\"']+)")


@dataclass(frozen=True)
class ApiKey:
    key_id: str
    secret: str = field(repr=False)  # keep secrets out of logs, reprs and tracebacks


class KeyPool:
    def __init__(self, secrets: list[str]) -> None:
        self._keys = tuple(ApiKey(key_id=f"key_{index}", secret=secret) for index, secret in enumerate(secrets, 1))

    def __iter__(self):  # type: ignore[no-untyped-def]
        return iter(self._keys)

    def __len__(self) -> int:
        return len(self._keys)

    def redact(self, text: str) -> str:
        """Remove any key material from text (provider error messages may echo the key or URL)."""
        for key in self._keys:
            text = text.replace(key.secret, f"<{key.key_id}>")
        return _KEY_LIKE.sub("<redacted>", text)
