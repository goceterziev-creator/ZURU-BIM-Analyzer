import json
from collections import Counter


def build_reports(analysis, filename):
    """Assemble product-facing reports and exports from deterministic analysis.

    Returns a dict with:
      - evidence_report_txt: human-readable text summary distinguishing source evidence
        from derived deterministic classifications and heuristics.
      - normalized_evidence_json: JSON string of the original normalized evidence (unchanged)
      - deterministic_classifications_json: JSON string of evidence_classifications
      - classification_counts: Counter mapping classification -> count
    """
    entity_stats = analysis.get("entity_stats", {})
    layer_stats = analysis.get("layer_stats", {})
    room_texts = analysis.get("room_texts", [])
    room_stats = analysis.get("room_label_stats", {})
    evidence_records = analysis.get("evidence_records", [])
    source_signals = analysis.get("source_signals", {})
    geometry_candidates = analysis.get("geometry_candidates", 0)

    # Deterministic classifications (should be provided by core)
    classifications = analysis.get("evidence_classifications", [])

    counts = Counter(c.get("classification", "unknown") for c in classifications)

    # Build a human-readable report that clearly separates source evidence from derived classification
    report_lines = []
    report_lines.append(f"ZURU BIM Analyzer Report: {filename}")
    report_lines.append("")
    report_lines.append("EVIDENCE-BOUND DXF FACTS (raw, normalized from DXF)")
    report_lines.append(f"Total DXF entities: {sum(entity_stats.values()) if hasattr(entity_stats, 'values') else sum(entity_stats)}")
    report_lines.append(f"Normalized evidence records: {len(evidence_records):,}")
    report_lines.append(f"TEXT/MTEXT labels: {len(room_texts):,}")
    report_lines.append(f"Top entity types: {dict(entity_stats.most_common(10)) if hasattr(entity_stats, 'most_common') else dict(entity_stats)}")
    report_lines.append(f"Top layers: {dict(layer_stats.most_common(10)) if hasattr(layer_stats, 'most_common') else dict(layer_stats)}")
    report_lines.append(f"Source signals: {source_signals}")
    report_lines.append("")
    report_lines.append("DETERMINISTIC EVIDENCE-BOUND CLASSIFICATIONS (accepted v1)")
    report_lines.append("The following classifications are derived deterministically from the normalized DXF evidence records using the accepted evidence classifier. These are NOT AI inferences; provenance lists the features that triggered each classification.")
    report_lines.append(f"Classification counts: {dict(counts)}")
    report_lines.append("")
    report_lines.append("BOUNDED HEURISTICS")
    report_lines.append(f"Geometry candidates (LWPOLYLINE + HATCH): {geometry_candidates}")
    report_lines.append(f"Room-label heuristics: {room_stats}")
    report_lines.append("")
    report_lines.append("Note: source signals, heuristics, and these deterministic classifications are not equivalent to validated BIM element classification. Gemini AI inference (optional) is separate and not required for these deterministic outputs.")

    evidence_report_txt = "\n".join(report_lines)

    # JSON artifacts
    normalized_evidence_json = json.dumps(evidence_records, ensure_ascii=False, indent=2)
    deterministic_classifications_json = json.dumps(classifications, ensure_ascii=False, indent=2)

    return {
        "evidence_report_txt": evidence_report_txt,
        "normalized_evidence_json": normalized_evidence_json,
        "deterministic_classifications_json": deterministic_classifications_json,
        "classification_counts": counts,
    }
