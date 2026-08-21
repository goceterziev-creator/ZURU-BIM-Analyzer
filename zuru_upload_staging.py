"""Bounded, process-local staging for session-independent mobile uploads.

The staging registry is intentionally independent from Streamlit session state.
It stores temporary files only until an owner explicitly claims them, and it
deletes every file on expiry, rejection, or successful consumption.
"""

from __future__ import annotations

from dataclasses import dataclass
import hmac
import os
from pathlib import Path
import re
import secrets
import shutil
import tempfile
import threading
import time


MAX_UPLOAD_BYTES = 200 * 1024 * 1024
DEFAULT_TTL_SECONDS = 10 * 60
DEFAULT_MAX_ENTRIES = 32
DEFAULT_MAX_STAGED_BYTES = 400 * 1024 * 1024
ALLOWED_EXTENSIONS = frozenset({"dxf", "dwg"})

_TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]{43}$")


class StagingError(Exception):
    """Base error for rejected staging operations."""


class InvalidUpload(StagingError):
    """Upload metadata, ownership, or state is invalid."""


class UploadNotFound(StagingError):
    """Upload or claim does not exist, expired, or was already consumed."""


class StagingCapacityExceeded(StagingError):
    """The bounded process-local staging capacity is exhausted."""


@dataclass(frozen=True)
class UploadIntent:
    upload_id: str
    owner_token: str
    filename: str
    extension: str
    declared_size: int
    created_at: float
    expires_at: float


@dataclass
class _StagedEntry:
    intent: UploadIntent
    path: Path | None = None
    stored_size: int = 0
    claim_token: str | None = None


@dataclass(frozen=True)
class PendingUpload:
    upload_id: str
    filename: str
    extension: str
    size: int
    expires_at: float
    ready: bool


class StagedUploadedFile:
    """Small adapter matching the existing UploadedFile fields ZURU consumes."""

    def __init__(self, *, filename: str, file_bytes: bytes):
        self.name = filename
        self.size = len(file_bytes)
        self.type = None
        self._file_bytes = file_bytes

    def getvalue(self) -> bytes:
        return self._file_bytes


def new_token() -> str:
    """Return a 256-bit URL-safe token with a fixed validated shape."""

    return secrets.token_urlsafe(32)


def is_valid_token(value: object) -> bool:
    return isinstance(value, str) and _TOKEN_RE.fullmatch(value) is not None


def normalize_filename(filename: object) -> tuple[str, str]:
    if not isinstance(filename, str) or not filename or "\x00" in filename:
        raise InvalidUpload("A valid filename is required.")

    normalized = Path(filename.replace("\\", "/")).name.strip()
    if not normalized or normalized in {".", ".."} or len(normalized) > 255:
        raise InvalidUpload("The filename is invalid.")

    if "." not in normalized:
        raise InvalidUpload("Only DXF and DWG files are accepted.")
    extension = normalized.rsplit(".", 1)[-1].lower()
    if extension not in ALLOWED_EXTENSIONS:
        raise InvalidUpload("Only DXF and DWG files are accepted.")
    return normalized, extension


class UploadStagingRegistry:
    """Thread-safe owner-bound registry with TTL and deterministic cleanup."""

    def __init__(
        self,
        *,
        root: str | Path | None = None,
        ttl_seconds: float = DEFAULT_TTL_SECONDS,
        max_entries: int = DEFAULT_MAX_ENTRIES,
        max_staged_bytes: int = DEFAULT_MAX_STAGED_BYTES,
    ):
        if ttl_seconds <= 0 or max_entries <= 0 or max_staged_bytes <= 0:
            raise ValueError("Staging bounds must be positive.")
        self._root = Path(root or Path(tempfile.gettempdir()) / "zuru-upload-staging")
        self._ttl_seconds = ttl_seconds
        self._max_entries = max_entries
        self._max_staged_bytes = max_staged_bytes
        self._entries: dict[str, _StagedEntry] = {}
        self._claims: dict[str, str] = {}
        self._lock = threading.RLock()

    @property
    def root(self) -> Path:
        return self._root

    def create_intent(
        self,
        *,
        owner_token: str,
        filename: object,
        declared_size: object,
        now: float | None = None,
    ) -> UploadIntent:
        self._require_token(owner_token)
        normalized, extension = normalize_filename(filename)
        if not isinstance(declared_size, int) or isinstance(declared_size, bool):
            raise InvalidUpload("The declared file size is invalid.")
        if declared_size <= 0 or declared_size > MAX_UPLOAD_BYTES:
            raise InvalidUpload("The file exceeds the 200 MB upload limit.")

        observed_at = time.monotonic() if now is None else now
        with self._lock:
            self._prune_locked(observed_at)
            if len(self._entries) >= self._max_entries:
                raise StagingCapacityExceeded("Temporary upload capacity is full.")
            if self._staged_bytes_locked() + declared_size > self._max_staged_bytes:
                raise StagingCapacityExceeded("Temporary upload capacity is full.")

            upload_id = new_token()
            intent = UploadIntent(
                upload_id=upload_id,
                owner_token=owner_token,
                filename=normalized,
                extension=extension,
                declared_size=declared_size,
                created_at=observed_at,
                expires_at=observed_at + self._ttl_seconds,
            )
            self._entries[upload_id] = _StagedEntry(intent=intent)
            return intent

    def store_stream(
        self,
        *,
        owner_token: str,
        upload_id: str,
        chunks,
        now: float | None = None,
    ) -> PendingUpload:
        """Store byte chunks once for an existing owner-bound upload intent."""

        self._require_token(owner_token)
        self._require_token(upload_id)
        observed_at = time.monotonic() if now is None else now

        with self._lock:
            self._prune_locked(observed_at)
            entry = self._owned_entry_locked(owner_token, upload_id)
            if entry.path is not None:
                raise InvalidUpload("This upload intent was already used.")
            self._root.mkdir(mode=0o700, parents=True, exist_ok=True)
            fd, raw_path = tempfile.mkstemp(prefix="upload-", dir=self._root)
            os.close(fd)
            path = Path(raw_path)

        total = 0
        try:
            with path.open("wb") as staged_file:
                for chunk in chunks:
                    if not isinstance(chunk, (bytes, bytearray, memoryview)):
                        raise InvalidUpload("The upload stream is invalid.")
                    total += len(chunk)
                    if total > MAX_UPLOAD_BYTES or total > entry.intent.declared_size:
                        raise InvalidUpload("The upload exceeded its declared size.")
                    staged_file.write(chunk)
            if total != entry.intent.declared_size:
                raise InvalidUpload("The uploaded size did not match its declaration.")

            with self._lock:
                current = self._owned_entry_locked(owner_token, upload_id)
                if current.path is not None:
                    raise InvalidUpload("This upload intent was already used.")
                current.path = path
                current.stored_size = total
                return self._pending_from_entry(current)
        except Exception:
            path.unlink(missing_ok=True)
            raise

    async def store_async_stream(
        self,
        *,
        owner_token: str,
        upload_id: str,
        chunks,
        now: float | None = None,
    ) -> PendingUpload:
        """Stream an ASGI request body to disk without buffering the full file."""

        self._require_token(owner_token)
        self._require_token(upload_id)
        observed_at = time.monotonic() if now is None else now

        with self._lock:
            self._prune_locked(observed_at)
            entry = self._owned_entry_locked(owner_token, upload_id)
            if entry.path is not None:
                raise InvalidUpload("This upload intent was already used.")
            self._root.mkdir(mode=0o700, parents=True, exist_ok=True)
            fd, raw_path = tempfile.mkstemp(prefix="upload-", dir=self._root)
            os.close(fd)
            path = Path(raw_path)

        total = 0
        try:
            with path.open("wb") as staged_file:
                async for chunk in chunks:
                    if not isinstance(chunk, (bytes, bytearray, memoryview)):
                        raise InvalidUpload("The upload stream is invalid.")
                    total += len(chunk)
                    if total > MAX_UPLOAD_BYTES or total > entry.intent.declared_size:
                        raise InvalidUpload("The upload exceeded its declared size.")
                    staged_file.write(chunk)
            if total != entry.intent.declared_size:
                raise InvalidUpload("The uploaded size did not match its declaration.")

            with self._lock:
                current = self._owned_entry_locked(owner_token, upload_id)
                if current.path is not None:
                    raise InvalidUpload("This upload intent was already used.")
                current.path = path
                current.stored_size = total
                return self._pending_from_entry(current)
        except Exception:
            path.unlink(missing_ok=True)
            raise

    def list_pending(
        self, *, owner_token: str, now: float | None = None
    ) -> list[PendingUpload]:
        self._require_token(owner_token)
        observed_at = time.monotonic() if now is None else now
        with self._lock:
            self._prune_locked(observed_at)
            owned = [
                self._pending_from_entry(entry)
                for entry in self._entries.values()
                if hmac.compare_digest(entry.intent.owner_token, owner_token)
            ]
            return sorted(owned, key=lambda item: (item.expires_at, item.upload_id))

    def create_claim(
        self,
        *,
        owner_token: str,
        upload_id: str,
        now: float | None = None,
    ) -> str:
        """Create one claim only after an explicit owner-confirmed action."""

        self._require_token(owner_token)
        self._require_token(upload_id)
        observed_at = time.monotonic() if now is None else now
        with self._lock:
            self._prune_locked(observed_at)
            entry = self._owned_entry_locked(owner_token, upload_id)
            if entry.path is None or entry.stored_size != entry.intent.declared_size:
                raise InvalidUpload("The upload is not ready.")
            if entry.claim_token is not None:
                raise InvalidUpload("This upload was already confirmed.")
            claim_token = new_token()
            entry.claim_token = claim_token
            self._claims[claim_token] = upload_id
            return claim_token

    def consume_claim(
        self, claim_token: str, *, now: float | None = None
    ) -> StagedUploadedFile:
        """Consume a single-use claim and delete its temporary file."""

        self._require_token(claim_token)
        observed_at = time.monotonic() if now is None else now
        with self._lock:
            self._prune_locked(observed_at)
            upload_id = self._claims.pop(claim_token, None)
            if upload_id is None:
                raise UploadNotFound("The staged upload claim is unavailable.")
            entry = self._entries.pop(upload_id, None)
            if entry is None or entry.path is None:
                raise UploadNotFound("The staged upload claim is unavailable.")
            path = entry.path
            filename = entry.intent.filename

        try:
            file_bytes = path.read_bytes()
            if len(file_bytes) != entry.intent.declared_size:
                raise InvalidUpload("The staged upload size changed unexpectedly.")
            return StagedUploadedFile(filename=filename, file_bytes=file_bytes)
        finally:
            path.unlink(missing_ok=True)

    def prune(self, *, now: float | None = None) -> int:
        observed_at = time.monotonic() if now is None else now
        with self._lock:
            return self._prune_locked(observed_at)

    def close(self) -> None:
        """Deterministically delete all registry-owned temporary data."""

        with self._lock:
            for entry in self._entries.values():
                self._delete_entry_file(entry)
            self._entries.clear()
            self._claims.clear()
        shutil.rmtree(self._root, ignore_errors=True)

    def __len__(self) -> int:
        with self._lock:
            return len(self._entries)

    def _owned_entry_locked(self, owner_token: str, upload_id: str) -> _StagedEntry:
        entry = self._entries.get(upload_id)
        if entry is None or not hmac.compare_digest(
            entry.intent.owner_token, owner_token
        ):
            raise UploadNotFound("The staged upload is unavailable.")
        return entry

    def _prune_locked(self, now: float) -> int:
        expired_ids = [
            upload_id
            for upload_id, entry in self._entries.items()
            if now >= entry.intent.expires_at
        ]
        for upload_id in expired_ids:
            entry = self._entries.pop(upload_id)
            self._delete_entry_file(entry)
            if entry.claim_token is not None:
                self._claims.pop(entry.claim_token, None)
        return len(expired_ids)

    def _staged_bytes_locked(self) -> int:
        return sum(entry.intent.declared_size for entry in self._entries.values())

    @staticmethod
    def _delete_entry_file(entry: _StagedEntry) -> None:
        if entry.path is not None:
            entry.path.unlink(missing_ok=True)

    @staticmethod
    def _pending_from_entry(entry: _StagedEntry) -> PendingUpload:
        return PendingUpload(
            upload_id=entry.intent.upload_id,
            filename=entry.intent.filename,
            extension=entry.intent.extension,
            size=entry.stored_size or entry.intent.declared_size,
            expires_at=entry.intent.expires_at,
            ready=entry.path is not None,
        )

    @staticmethod
    def _require_token(token: object) -> None:
        if not is_valid_token(token):
            raise InvalidUpload("The upload token is invalid.")


UPLOAD_STAGING_REGISTRY = UploadStagingRegistry()
