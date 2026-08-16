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
  (conflicting evidence).  Never guess from generic INSERT or geometry types alone.

Provenance: list of dicts {"fact": <field>, "value": <value>} indicating which
source facts triggered the classification. The original evidence records are
preserved untouched.
"""
from typing import List, Dict
from zuru_core import ROOM_PATTERNS

# simple substring keywords for furnishing detection — conservative and deterministic
FURNISH_KEYWORDS = ("chair", "table", "sofa", "bed", "cabinet", "armchair")

_CLASSES = {"door", "window", "wall", "furnishing", "room_label", "unknown"}


def _match_room_text(text: str) -> bool:
    if not text:
        return False
    for _, pattern in ROOM_PATTERNS.items():
        if pattern.search(text):
            return True
    return False


def classify_evidence(evidence_records: List[Dict]) -> List[Dict]:
    """Classify each evidence record conservatively.

    Returns a list of results with keys:
      - record: original evidence record (unchanged)
      - classification: one of supported classes
      - provenance: list of {fact, value} that triggered the classification
    """
    results = []
    for record in evidence_records:
        candidates = []
        prov = []
        etype = record.get("entity_type")
        layer = record.get("layer")
        block = record.get("block_name")
        text = record.get("text")

        # room_label: TEXT/MTEXT matching patterns or on _room layer
        if etype in ("TEXT", "MTEXT") and (_match_room_text(text) or (layer and layer.casefold() == "_room")):
            candidates.append("room_label")
            prov.append({"fact": "text", "value": text})
            if layer:
                prov.append({"fact": "layer", "value": layer})

        # door: INSERT with explicit door layer or block name containing 'door'
        if etype == "INSERT":
            if layer and layer.casefold() == "_door":
                candidates.append("door")
                prov.append({"fact": "layer", "value": layer})
            if block and "door" in block.casefold():
                candidates.append("door")
                prov.append({"fact": "block_name", "value": block})

            # window
            if layer and layer.casefold() == "_window":
                candidates.append("window")
                prov.append({"fact": "layer", "value": layer})
            if block and "window" in block.casefold():
                candidates.append("window")
                prov.append({"fact": "block_name", "value": block})

            # furnishing: explicit furnish layer or furnishing keywords in block name
            if layer and layer.casefold() == "_furnish":
                candidates.append("furnishing")
                prov.append({"fact": "layer", "value": layer})
            if block:
                bl = block.casefold()
                if any(k in bl for k in FURNISH_KEYWORDS):
                    candidates.append("furnishing")
                    prov.append({"fact": "block_name", "value": block})

        # wall: geometric entities but only when on explicit _wall layer
        if etype in ("LINE", "LWPOLYLINE", "HATCH") and layer and layer.casefold() == "_wall":
            candidates.append("wall")
            prov.append({"fact": "layer", "value": layer})
            prov.append({"fact": "entity_type", "value": etype})

        # Canonicalize candidate list: unique
        unique_candidates = []
        for c in candidates:
            if c not in unique_candidates:
                unique_candidates.append(c)

        # Decide result: unknown if none or >1 (conflict)
        if len(unique_candidates) == 1:
            classification = unique_candidates[0]
            provenance = prov
        else:
            classification = "unknown"
            # include the facts that were considered, even if conflicting or empty
            provenance = prov or [
                {"fact": "entity_type", "value": etype},
                {"fact": "layer", "value": layer},
                {"fact": "block_name", "value": block},
                {"fact": "text", "value": text},
            ]

        results.append({"record": record, "classification": classification, "provenance": provenance})

    return results
