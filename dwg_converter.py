"""Deterministic fake DWG converter for tests/demo only.

This module is intentionally simple and deterministic. Real converters are
external and must be explicitly configured. Do NOT enable this in CI unless
intentionally injected by tests.
"""

class FakeConverter:
    """Simple converter that returns a placeholder DXF byte payload.

    Tests should inject this converter to verify the ingestion routing logic
    without depending on external binaries.
    """

    def convert_dwg_to_dxf(self, dwg_bytes: bytes) -> bytes:
        # Deterministic fake output that test stubs will notice. This is not a
        # valid DXF for ezdxf parsing; tests that need the analysis to run
        # should monkeypatch the analyzer instead of relying on real parsing.
        return b"FAKE_CONVERTED_DXF_BYTES_FROM_DWG"


# Expose a simple callable too
def convert_dwg_to_dxf(dwg_bytes: bytes) -> bytes:
    return FakeConverter().convert_dwg_to_dxf(dwg_bytes)
