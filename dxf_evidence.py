"""Deterministic normalization of raw DXF entities into evidence records.

This module records facts exposed by DXF/ezdxf. It intentionally does not
classify architectural meaning (door, room, wall, etc.).
"""


def _safe_dxf_attr(entity, name):
    dxf = getattr(entity, "dxf", None)
    if dxf is None:
        return None
    try:
        value = getattr(dxf, name)
    except (AttributeError, ValueError, TypeError):
        return None
    if value is None:
        return None
    return str(value)


def normalize_entity(entity):
    """Return a JSON-serializable evidence record for one DXF entity."""
    entity_type = entity.dxftype()
    record = {
        "entity_type": entity_type,
        "layer": _safe_dxf_attr(entity, "layer"),
        "handle": _safe_dxf_attr(entity, "handle"),
        "block_name": None,
        "text": None,
        "source": "DXF",
    }

    if entity_type == "INSERT":
        record["block_name"] = _safe_dxf_attr(entity, "name")

    if entity_type in ("TEXT", "MTEXT"):
        text = _safe_dxf_attr(entity, "text")
        record["text"] = text.strip() if text else None

    return record


def normalize_modelspace(modelspace):
    """Normalize modelspace in source iteration order without inference."""
    return [normalize_entity(entity) for entity in modelspace]
