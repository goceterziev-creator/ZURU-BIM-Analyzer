import pytest

import zuru_ingest


class DummyConverter:
    def __init__(self):
        self.called_with = None

    def convert_dwg_to_dxf(self, data: bytes) -> bytes:
        self.called_with = data
        return b"CONVERTED_DXF_BYTES"


def test_dwg_converter_unavailable_raises():
    # Ensure no env var influences detection
    import os

    os.environ.pop("DWG_CONVERTER_IMPL", None)
    os.environ.pop("DWG_CONVERTER_ENABLED", None)

    with pytest.raises(zuru_ingest.DwgConverterUnavailableError):
        zuru_ingest.ingest_file_bytes("file.dwg", b"irrelevant")


def test_dwg_with_injected_converter_calls_analysis(monkeypatch):
    dummy = DummyConverter()

    called = {}

    def fake_analyze(dxf_bytes):
        # confirm analyze got the converted bytes
        assert dxf_bytes == b"CONVERTED_DXF_BYTES"
        called["analyzed"] = True
        return {"entity_stats": {}, "layer_stats": {}, "room_texts": [], "room_label_stats": {}, "geometry_candidates": 0, "source_signals": {}, "evidence_records": [], "evidence_classifications": []}

    # Patch the analyze function used by the ingest module
    monkeypatch.setattr(zuru_ingest, "analyze_dxf_bytes", fake_analyze)

    result = zuru_ingest.ingest_file_bytes("file.dwg", b"dwg-data", converter=dummy)

    assert called.get("analyzed") is True
    assert "ingestion_provenance" in result
    assert result["ingestion_provenance"]["original_format"] == "dwg"
    assert result["ingestion_provenance"]["conversion"] == "dwg->dxf"


def test_dxf_route_calls_analyzer_directly(monkeypatch):
    called = {}

    def fake_analyze(dxf_bytes):
        called["bytes"] = dxf_bytes
        return {"entity_stats": {}, "layer_stats": {}, "room_texts": [], "room_label_stats": {}, "geometry_candidates": 0, "source_signals": {}, "evidence_records": [], "evidence_classifications": []}

    monkeypatch.setattr(zuru_ingest, "analyze_dxf_bytes", fake_analyze)

    data = b"RAW_DXF_BYTES"
    result = zuru_ingest.ingest_file_bytes("drawing.dxf", data)

    assert called.get("bytes") == data
    assert "ingestion_provenance" not in result
