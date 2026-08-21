"""Bounded metadata-only tracking for the Android upload recovery experiment."""

from __future__ import annotations

from dataclasses import dataclass
import re
import threading
import time


_OWNER_TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]{32}$")
_SESSION_ID_RE = re.compile(r"^[0-9a-f]{32}$")


@dataclass(frozen=True)
class UploadSessionObservation:
    """Result of associating one browser owner token with one live session."""

    session_replaced: bool
    previous_session_id: str | None


class UploadSessionRegistry:
    """Track session ownership without retaining filenames or file data.

    Entries expire after ``ttl_seconds`` and the registry has a hard entry cap.
    Cleanup is deterministic on every observation and explicit ``prune`` call.
    """

    def __init__(self, *, ttl_seconds: float = 15 * 60, max_entries: int = 2048):
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be positive")
        if max_entries <= 0:
            raise ValueError("max_entries must be positive")
        self._ttl_seconds = ttl_seconds
        self._max_entries = max_entries
        self._entries: dict[str, tuple[str, float]] = {}
        self._lock = threading.Lock()

    def observe(
        self,
        owner_token: str,
        session_id: str,
        *,
        now: float | None = None,
    ) -> UploadSessionObservation:
        """Record a live session and report whether it replaced an unexpired one."""

        if not is_valid_owner_token(owner_token):
            raise ValueError("invalid owner token")
        if not is_valid_session_id(session_id):
            raise ValueError("invalid session id")

        observed_at = time.monotonic() if now is None else now
        with self._lock:
            self._prune_locked(observed_at)
            previous = self._entries.get(owner_token)
            previous_session_id = previous[0] if previous is not None else None
            session_replaced = (
                previous_session_id is not None and previous_session_id != session_id
            )
            self._entries[owner_token] = (session_id, observed_at)
            self._enforce_capacity_locked()

        return UploadSessionObservation(session_replaced, previous_session_id)

    def prune(self, *, now: float | None = None) -> int:
        """Remove expired entries and return the number removed."""

        observed_at = time.monotonic() if now is None else now
        with self._lock:
            return self._prune_locked(observed_at)

    def __len__(self) -> int:
        with self._lock:
            return len(self._entries)

    def _prune_locked(self, now: float) -> int:
        expired = [
            token
            for token, (_, last_seen) in self._entries.items()
            if now - last_seen >= self._ttl_seconds
        ]
        for token in expired:
            del self._entries[token]
        return len(expired)

    def _enforce_capacity_locked(self) -> None:
        overflow = len(self._entries) - self._max_entries
        if overflow <= 0:
            return
        oldest = sorted(self._entries.items(), key=lambda item: (item[1][1], item[0]))
        for token, _ in oldest[:overflow]:
            del self._entries[token]


def is_valid_owner_token(value: object) -> bool:
    return isinstance(value, str) and _OWNER_TOKEN_RE.fullmatch(value) is not None


def is_valid_session_id(value: object) -> bool:
    return isinstance(value, str) and _SESSION_ID_RE.fullmatch(value) is not None


UPLOAD_SESSION_REGISTRY = UploadSessionRegistry()
