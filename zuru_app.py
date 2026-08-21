"""ASGI entry point for the bounded mobile upload-staging experiment."""

import asyncio
from contextlib import asynccontextmanager
from contextlib import suppress

import streamlit as st

from zuru_upload_routes import create_upload_routes
from zuru_upload_staging import UPLOAD_STAGING_REGISTRY


@asynccontextmanager
async def lifespan(_app):
    async def prune_expired_uploads():
        while True:
            await asyncio.sleep(30)
            UPLOAD_STAGING_REGISTRY.prune()

    cleanup_task = asyncio.create_task(prune_expired_uploads())
    try:
        yield
    finally:
        cleanup_task.cancel()
        with suppress(asyncio.CancelledError):
            await cleanup_task
        UPLOAD_STAGING_REGISTRY.close()


app = st.App(
    "zuru_simple.py",
    routes=create_upload_routes(),
    lifespan=lifespan,
)
