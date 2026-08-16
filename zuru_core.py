"""Core deterministic DXF analysis for ZURU BIM Analyzer.

The core separates source facts from heuristics so the UI can communicate
what is observed directly in DXF versus what is inferred from naming rules.
"""

from collections import Counter
import os
import re
import tempfile

import ezdxf

from dxf_evidence import normalize_modelspace

ROOM_PATTERNS = {
    "🛁 Бани/ВЦ": re.compile(r"(БАНЯ|ВЦ|ТОАЛЕТНА|WC).*?[-№\s]*(\d+)", re.I),
    "🍳 Кухни": re.compile(r"(КУХНЯ).*?[-№\s]*(\d+)", re.I),
    "🛏️ Спални": re.compile(r"(СПАЛНЯ|СТАЯ).*?[-№\s]*(\d+)", re.I),
    "🏠 Хол": re.compile(r"(ХОЛ|ГОСТИНСКИ).*?[-№\s]*(\d+)", re.I),
    "🚪 Коридори": re.compile(r"(КОРИДОР).*?[-№\s]*(\d+)", re.I),
}


def classify_room_labels(room_texts):
    """Count room-label heuristics without pretending they are geometry facts."""
    return {
        label: sum(1 for text in room_texts if pattern.search(text or ""))
        for label, pattern in ROOM_PATTERNS.items()
    }


def _layer_count(layer_stats, layer_name):
    """Case-insensitive exact layer-name count."""
    target = layer_name.casefold()
    return sum(count for name, count in layer_stats.items() if str(name).casefold() == target)


def analyze_dxf_bytes(file_bytes):
    """Parse DXF bytes and return deterministic evidence plus bounded heuristics."""
    with tempfile.NamedTemporaryFile(suffix=".dxf", delete=False) as temp_file:
        temp_file.write(file_bytes)
        temp_filename = temp_file.name

    try:
        doc = ezdxf.readfile(temp_filename)
        modelspace = doc.modelspace()
        evidence_records = normalize_modelspace(modelspace)

        entity_stats = Counter(record["entity_type"] for record in evidence_records)
        layer_stats = Counter(record["layer"] for record in evidence_records if record["layer"] is not None)
        room_texts = [record["text"] for record in evidence_records if record["text"]]

        geometry_candidates = sum(
            1 for record in evidence_records if record["entity_type"] in {"LWPOLYLINE", "HATCH"}
        )

        source_signals = {
            "_door layer entities": _layer_count(layer_stats, "_door"),
            "INSERT entities": entity_stats.get("INSERT", 0),
            "_window layer entities": _layer_count(layer_stats, "_window"),
            "_wall layer entities": _layer_count(layer_stats, "_wall"),
            "_furnish layer entities": _layer_count(layer_stats, "_furnish"),
        }

        # Deterministic evidence-bound classifications (separate from any AI inference)
        from evidence_classifier import classify_evidence

        evidence_classifications = classify_evidence(evidence_records)

        return {
            "entity_stats": entity_stats,
            "layer_stats": layer_stats,
            "room_texts": room_texts,
            "room_label_stats": classify_room_labels(room_texts),
            "geometry_candidates": geometry_candidates,
            "source_signals": source_signals,
            "evidence_records": evidence_records,
            # Deterministic classifications derived only from normalized evidence_records.
            # Each entry includes: record (original evidence record, preserved unchanged),
            # classification (one of door/window/wall/furnishing/room_label/unknown),
            # provenance: list of facts that triggered the classification.
            "evidence_classifications": evidence_classifications,
        }
    finally:
        os.unlink(temp_filename)
