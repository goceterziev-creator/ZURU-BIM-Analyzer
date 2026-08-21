"""Streamlit component bridge for the session-independent upload surface."""

from __future__ import annotations

from pathlib import Path

import streamlit.components.v1 as components


_COMPONENT_PATH = Path(__file__).with_name("zuru_staged_uploader_component")
_staged_uploader_component = components.declare_component(
    "zuru_staged_uploader",
    path=str(_COMPONENT_PATH),
)


def staged_uploader(*, clear_claim: bool, key: str):
    """Render the uploader and return a claim through component state only."""

    return _staged_uploader_component(
        clear_claim=clear_claim,
        default=None,
        key=key,
    )
