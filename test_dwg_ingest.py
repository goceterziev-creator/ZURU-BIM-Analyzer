import os
import unittest
from unittest import mock

import zuru_ingest


class DummyConverter:
    def __init__(self):
        self.called_with = None

    def convert_dwg_to_dxf(self, data: bytes) -> bytes:
        self.called_with = data
        return b"CONVERTED_DXF_BYTES"


class TestDwgIngest(unittest.TestCase):
    def setUp(self):
        # Ensure environment does not influence converter detection by default
        os.environ.pop("DWG_CONVERTER_IMPL", None)
        os.environ.pop("DWG_CONVERTER_ENABLED", None)

    def test_dwg_converter_unavailable_raises(self):
        with self.assertRaises(zuru_ingest.DwgConverterUnavailableError):
            zuru_ingest.ingest_file_bytes("file.dwg", b"irrelevant")

    def test_dwg_with_injected_converter_calls_analysis(self):
        dummy = DummyConverter()

        def fake_analyze(dxf_bytes):
            # confirm analyze got the converted bytes
            self.assertEqual(dxf_bytes, b"CONVERTED_DXF_BYTES")
            return {
                "entity_stats": {},
                "layer_stats": {},
                "room_texts": [],
                "room_label_stats": {},
                "geometry_candidates": 0,
                "source_signals": {},
                "evidence_records": [],
                "evidence_classifications": [],
            }

        with mock.patch("zuru_ingest.analyze_dxf_bytes", side_effect=fake_analyze, create=True):
            result = zuru_ingest.ingest_file_bytes("file.dwg", b"dwg-data", converter=dummy)

        self.assertIn("ingestion_provenance", result)
        self.assertEqual(result["ingestion_provenance"]["original_format"], "dwg")
        self.assertEqual(result["ingestion_provenance"]["conversion"], "dwg->dxf")

    def test_dxf_route_calls_analyzer_directly(self):
        def fake_analyze(dxf_bytes):
            return {"analyzed_bytes": dxf_bytes}

        with mock.patch("zuru_ingest.analyze_dxf_bytes", side_effect=fake_analyze, create=True) as patched:
            data = b"RAW_DXF_BYTES"
            result = zuru_ingest.ingest_file_bytes("drawing.dxf", data)

        patched.assert_called_once_with(data)
        self.assertNotIn("ingestion_provenance", result)

    def test_failed_conversion_raises_and_does_not_call_analyzer(self):
        class FailingConverter:
            def convert_dwg_to_dxf(self, data: bytes) -> bytes:
                raise RuntimeError("conversion failed")

        called = {"analyzed": False}

        def fake_analyze(dxf_bytes):
            called["analyzed"] = True
            return {}

        with mock.patch("zuru_ingest.analyze_dxf_bytes", side_effect=fake_analyze, create=True):
            with self.assertRaises(zuru_ingest.DwgConversionError):
                zuru_ingest.ingest_file_bytes("file.dwg", b"dwg-data", converter=FailingConverter())

        self.assertFalse(called["analyzed"])


if __name__ == "__main__":
    unittest.main()
