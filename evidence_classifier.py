"""Deterministic, evidence-bound classification v1.

Consumes normalized evidence records from dxf_evidence.normalize_modelspace
and produces conservative classifications with provenance.

Classes: door, window, wall, furnishing, room_label, unknown

Rules (v1):
- door: INSERT with layer == "_door" (case-insensitive) OR INSERT with block_name
  containing "door" (case-insensitive).
- window: INSERT with layer == "_window" OR INSERT with block_name containing "window".
- furnishing: INSERT with layer == "_furnish" OR INSERT with block_name matching
  common furnishing keywords (chair, table, sofa, bed, cabinet).
- wall: LINE, LWPOLYLINE, HATCH with layer == "_wall".
- room_label: TEXT or MTEXT where text matches ROOM_PATTERNS (imported from zuru_core)
  OR text-bearing entity on layer == "_room".
- unknown: returned whenever no rule matches or more than one class would match
  (conflicting evidence). Never guess from generic INSERT or geometry types alone.

Provenance: list of dicts {"fact": <field>, "value": <value>} containing only
source facts that actually triggered the selected classification. The original
normalized evidence records are preserved untouched.
"""
from typing import Dict, List

from zuru_core import ROOM_PATTERNS


FURNISH_KEYWORDS = ("chair", "table", "sofa", "bed", "cabinet", "armchair")


def _match_room_text(text: str) -> bool:
    if not text:
        return False
    return any(pattern.search(text) for pattern in ROOM_PATTERNS.values())


def classify_evidence(evidence_records: List[Dict]) -> List[Dict]:
    """Classify normalized evidence records conservatively and deterministically."""
    results = []

    for record in evidence_records:
        candidates = []
        prov = []
        etype = record.get("entity_type")
        layer = record.get("layer")
        block = record.get("block_name")
        text = record.get("text")

        if etype in ("TEXT", "MTEXT"):
            text_matches_room = _match_room_text(text)
            layer_marks_room = bool(layer and layer.casefold() == "_room")
            if text_matches_room or layer_marks_room:
                candidates.append("room_label")
                if text_matches_room:
                    prov.append({"fact": "text", "value": text})
                if layer_marks_room:
                    prov.append({"fact": "layer", "value": layer})

        if etype == "INSERT":
            if layer and layer.casefold() == "_door":
                candidates.append("door")
                prov.append({"fact": "layer", "value": layer})
            if block and "door" in block.casefold():
                candidates.append("door")
                prov.append({"fact": "block_name", "value": block})

            if layer and layer.casefold() == "_window":
                candidates.append("window")
                prov.append({"fact": "layer", "value": layer})
            if block and "window" in block.casefold():
                candidates.append("window")
                prov.append({"fact": "block_name", "value": block})

            if layer and layer.casefold() == "_furnish":
                candidates.append("furnishing")
                prov.append({"fact": "layer", "value": layer})
            if block:
                block_folded = block.casefold()
                if any(keyword in block_folded for keyword in FURNISH_KEYWORDS):
                    candidates.append("furnishing")
                    prov.append({"fact": "block_name", "value": block})

        if etype in ("LINE", "LWPOLYLINE", "HATCH") and layer and layer.casefold() == "_wall":
            candidates.append("wall")
            prov.append({"fact": "layer", "value": layer})
            prov.append({"fact": "entity_type", "value": etype})

        unique_candidates = []
        for candidate in candidates:
            if candidate not in unique_candidates:
                unique_candidates.append(candidate)

        if len(unique_candidates) == 1:
            classification = unique_candidates[0]
            provenance = prov
        else:
            classification = "unknown"
            provenance = prov or [
                {"fact": "entity_type", "value": etype},
                {"fact": "layer", "value": layer},
                {"fact": "block_name", "value": block},
                {"fact": "text", "value": text},
            ]

        results.append(
            {
                "record": record,
                "classification": classification,
                "provenance": provenance,
            }
        )

    return results
