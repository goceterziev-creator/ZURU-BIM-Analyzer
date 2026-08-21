"""Protected ASGI routes for the bounded Android upload-staging experiment."""

from __future__ import annotations

import hmac
import time
from urllib.parse import urlsplit

from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from zuru_upload_staging import (
    InvalidUpload,
    MAX_UPLOAD_BYTES,
    StagingCapacityExceeded,
    StagingError,
    UPLOAD_STAGING_REGISTRY,
    UploadNotFound,
    UploadStagingRegistry,
    is_valid_token,
    new_token,
)


API_PREFIX = "/api/zuru-mobile-upload"
OWNER_COOKIE = "zuru_stage_owner"
XSRF_COOKIE = "zuru_stage_xsrf"
COOKIE_MAX_AGE_SECONDS = 60 * 60


def _json(payload: dict, status_code: int = 200) -> JSONResponse:
    response = JSONResponse(payload, status_code=status_code)
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


def _request_is_secure(request: Request) -> bool:
    forwarded = request.headers.get("x-forwarded-proto", "")
    if forwarded:
        return forwarded.split(",", 1)[0].strip().lower() == "https"
    return request.url.scheme == "https"


def _expected_origin(request: Request) -> str:
    scheme = "https" if _request_is_secure(request) else "http"
    return f"{scheme}://{request.headers.get('host', '')}"


def _same_origin(request: Request) -> bool:
    origin = request.headers.get("origin")
    if not origin:
        return False
    try:
        actual = urlsplit(origin)
        expected = urlsplit(_expected_origin(request))
    except ValueError:
        return False
    return (
        actual.scheme.lower() == expected.scheme.lower()
        and actual.netloc.lower() == expected.netloc.lower()
        and actual.path in {"", "/"}
    )


def _owner_token(request: Request) -> str:
    owner = request.cookies.get(OWNER_COOKIE)
    if not is_valid_token(owner):
        raise InvalidUpload("The browser upload owner is unavailable.")
    return owner


def _require_mutation_security(request: Request) -> str:
    if not _same_origin(request):
        raise InvalidUpload("The upload request origin is invalid.")
    owner = _owner_token(request)
    cookie_token = request.cookies.get(XSRF_COOKIE)
    header_token = request.headers.get("x-zuru-xsrf")
    if (
        not is_valid_token(cookie_token)
        or not is_valid_token(header_token)
        or not hmac.compare_digest(cookie_token, header_token)
    ):
        raise InvalidUpload("The upload request security token is invalid.")
    return owner


def _error_response(exc: Exception) -> JSONResponse:
    if isinstance(exc, UploadNotFound):
        return _json({"error": "upload_unavailable"}, 404)
    if isinstance(exc, StagingCapacityExceeded):
        return _json({"error": "staging_capacity_exceeded"}, 503)
    if isinstance(exc, InvalidUpload):
        return _json({"error": "invalid_upload"}, 400)
    return _json({"error": "upload_failed"}, 500)


def create_upload_routes(
    registry: UploadStagingRegistry = UPLOAD_STAGING_REGISTRY,
) -> list[Route]:
    async def bootstrap(request: Request) -> JSONResponse:
        owner = request.cookies.get(OWNER_COOKIE)
        if not is_valid_token(owner):
            owner = new_token()
        xsrf = request.cookies.get(XSRF_COOKIE)
        if not is_valid_token(xsrf):
            xsrf = new_token()

        response = _json(
            {
                "xsrf_token": xsrf,
                "max_upload_bytes": MAX_UPLOAD_BYTES,
                "accepted_extensions": ["dxf", "dwg"],
            }
        )
        secure = _request_is_secure(request)
        response.set_cookie(
            OWNER_COOKIE,
            owner,
            max_age=COOKIE_MAX_AGE_SECONDS,
            httponly=True,
            secure=secure,
            samesite="strict",
            path="/",
        )
        response.set_cookie(
            XSRF_COOKIE,
            xsrf,
            max_age=COOKIE_MAX_AGE_SECONDS,
            httponly=False,
            secure=secure,
            samesite="strict",
            path="/",
        )
        return response

    async def create_intent(request: Request) -> JSONResponse:
        try:
            owner = _require_mutation_security(request)
            if request.headers.get("content-type", "").split(";", 1)[0].strip() != "application/json":
                raise InvalidUpload("Upload intent metadata must be JSON.")
            payload = await request.json()
            if not isinstance(payload, dict):
                raise InvalidUpload("Upload intent metadata is invalid.")
            intent = registry.create_intent(
                owner_token=owner,
                filename=payload.get("filename"),
                declared_size=payload.get("size"),
            )
            return _json(
                {
                    "upload_id": intent.upload_id,
                    "filename": intent.filename,
                    "size": intent.declared_size,
                    "expires_in_seconds": int(intent.expires_at - time.monotonic()),
                },
                201,
            )
        except (StagingError, ValueError, TypeError) as exc:
            return _error_response(exc)

    async def upload_bytes(request: Request) -> JSONResponse:
        try:
            owner = _require_mutation_security(request)
            upload_id = request.path_params["upload_id"]
            if request.headers.get("content-type", "").split(";", 1)[0].strip() != "application/octet-stream":
                raise InvalidUpload("The upload content type is invalid.")
            content_length = request.headers.get("content-length")
            if content_length is not None:
                try:
                    declared_http_size = int(content_length)
                except ValueError as exc:
                    raise InvalidUpload("The upload content length is invalid.") from exc
                if declared_http_size <= 0 or declared_http_size > MAX_UPLOAD_BYTES:
                    raise InvalidUpload("The upload exceeds the 200 MB limit.")

            pending = await registry.store_async_stream(
                owner_token=owner,
                upload_id=upload_id,
                chunks=request.stream(),
            )
            return _json(
                {
                    "upload_id": pending.upload_id,
                    "filename": pending.filename,
                    "size": pending.size,
                    "ready": pending.ready,
                }
            )
        except (StagingError, ValueError, TypeError) as exc:
            return _error_response(exc)

    async def pending(request: Request) -> JSONResponse:
        try:
            owner = _owner_token(request)
            items = registry.list_pending(owner_token=owner)
            return _json(
                {
                    "uploads": [
                        {
                            "upload_id": item.upload_id,
                            "filename": item.filename,
                            "size": item.size,
                            "ready": item.ready,
                            "expires_in_seconds": max(
                                0, int(item.expires_at - time.monotonic())
                            ),
                        }
                        for item in items
                    ]
                }
            )
        except (StagingError, ValueError, TypeError) as exc:
            return _error_response(exc)

    async def claim(request: Request) -> JSONResponse:
        try:
            owner = _require_mutation_security(request)
            claim_token = registry.create_claim(
                owner_token=owner,
                upload_id=request.path_params["upload_id"],
            )
            return _json({"claim_token": claim_token})
        except (StagingError, ValueError, TypeError) as exc:
            return _error_response(exc)

    return [
        Route(f"{API_PREFIX}/bootstrap", bootstrap, methods=["GET"]),
        Route(f"{API_PREFIX}/intents", create_intent, methods=["POST"]),
        Route(
            f"{API_PREFIX}/intents/{{upload_id}}/bytes",
            upload_bytes,
            methods=["PUT"],
        ),
        Route(f"{API_PREFIX}/pending", pending, methods=["GET"]),
        Route(
            f"{API_PREFIX}/intents/{{upload_id}}/claim",
            claim,
            methods=["POST"],
        ),
    ]
