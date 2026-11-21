"""Parser for the X-Simulate-Failure test hook.

Format: comma-separated ``<key_id>=<status>`` pairs, where ``<key_id>`` is ``key_N`` or ``*``
(every key) and ``<status>`` is one of 429, 500, 502, 503. An explicit key entry takes
precedence over ``*``. The resulting plan is a value object that lives for a single request,
so a simulated failure can never leak into another request or mark a real key as unhealthy.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

SIMULATION_HEADER = "X-Simulate-Failure"
SUPPORTED_STATUSES = frozenset({429, 500, 502, 503})
_KEY_ID_PATTERN = re.compile(r"^(\*|key_[1-9][0-9]*)$")


class InvalidSimulationHeader(ValueError):
    pass


@dataclass(frozen=True)
class FailurePlan:
    per_key: dict[str, int] = field(default_factory=dict)
    wildcard: int | None = None

    def status_for(self, key_id: str) -> int | None:
        return self.per_key.get(key_id, self.wildcard)

    @property
    def is_active(self) -> bool:
        return bool(self.per_key) or self.wildcard is not None


def parse_failure_header(raw: str) -> FailurePlan:
    per_key: dict[str, int] = {}
    wildcard: int | None = None
    for entry in (part.strip() for part in raw.split(",")):
        if not entry:
            continue
        key_id, separator, status_text = (piece.strip() for piece in entry.partition("="))
        if not separator or not _KEY_ID_PATTERN.match(key_id):
            raise InvalidSimulationHeader(
                f"invalid entry {entry!r}; expected <key_id>=<status>, e.g. key_1=429 or *=503"
            )
        if not status_text.isdigit() or int(status_text) not in SUPPORTED_STATUSES:
            raise InvalidSimulationHeader(
                f"unsupported status {status_text!r}; use one of {sorted(SUPPORTED_STATUSES)}"
            )
        if key_id == "*":
            wildcard = int(status_text)
        else:
            per_key[key_id] = int(status_text)
    return FailurePlan(per_key=per_key, wildcard=wildcard)
