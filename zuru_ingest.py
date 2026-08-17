import importlib
import os
from typing import Optional

# Importing analyze_dxf_bytes lazily inside functions to avoid importing ezdxf at module import time
# (tests inject or patch the analyzer; production will import when needed)



class DwgConverterUnavailableError(Exception):
    """Raised when a DWG converter is not configured or explicitly unavailable."""


class DwgConversionError(Exception):
    """Raised when a configured DWG converter fails during conversion."""


def is_converter_configured() -> bool:
    """Detect whether a converter implementation is configured via environment.

    Detection is explicit: set DWG_CONVERTER_IMPL to a python module path that
    exposes a callable `convert_dwg_to_dxf(bytes) -> bytes`, or set
    DWG_CONVERTER_ENABLED=1 to indicate an externally-managed converter is
    available (executor-managed). Tests should inject a converter directly.
    """
    impl = os.getenv("DWG_CONVERTER_IMPL")
    enabled_flag = os.getenv("DWG_CONVERTER_ENABLED")
    return bool(impl) or (enabled_flag == "1")


def _load_configured_converter():
    impl = os.getenv("DWG_CONVERTER_IMPL")
    if not impl:
        return None
    try:
        module = importlib.import_module(impl)
        # Accept either a function or a module exposing convert_dwg_to_dxf
        if hasattr(module, "convert_dwg_to_dxf"):
            return module
        # Or an object named "Converter" with method convert_dwg_to_dxf
        if hasattr(module, "Converter"):
            return module.Converter()
        return None
    except Exception:
        return None


def ingest_file_bytes(filename: str, file_bytes: bytes, converter: Optional[object] = None) -> dict:
    """Product-facing ingestion router.

    - DXF files: passed directly to the canonical analyze_dxf_bytes() path.
    - DWG files: routed through a configured/injected converter to produce DXF
      bytes, which are then passed to analyze_dxf_bytes(). The returned result
      always includes deterministic analysis output; when a DWG conversion
      occurred, an `ingestion_provenance` key is added describing the
      conversion provenance.

    If no converter is available for DWG, raises DwgConverterUnavailableError.
    If converter fails, raises DwgConversionError.
    """
    if "." not in filename:
        ext = ""
    else:
        ext = filename.rsplit(".", 1)[-1].lower()

    if ext == "dxf":
        # Canonical DXF path — preserve deterministic behavior
        # Allow tests to inject a fake analyzer by setting `zuru_ingest.analyze_dxf_bytes`.
        if "analyze_dxf_bytes" in globals():
            analysis = analyze_dxf_bytes(file_bytes)
        else:
            import importlib
            analysis = importlib.import_module("zuru_core").analyze_dxf_bytes(file_bytes)
        return analysis

    if ext == "dwg":
        # Determine converter to use
        conv = converter or _load_configured_converter()
        if conv is None:
            raise DwgConverterUnavailableError("DWG converter not configured or unavailable")

        # Attempt conversion
        try:
            # Support either a function or object with method
            if callable(getattr(conv, "convert_dwg_to_dxf", None)):
                dxf_bytes = conv.convert_dwg_to_dxf(file_bytes)
            elif callable(conv):
                dxf_bytes = conv(file_bytes)
            else:
                raise DwgConversionError("Configured converter does not expose convert_dwg_to_dxf")

            if not isinstance(dxf_bytes, (bytes, bytearray)):
                raise DwgConversionError("Converter did not return bytes")
        except DwgConversionError:
            raise
        except Exception as exc:
            raise DwgConversionError(f"Converter failed: {exc}")

        # Now call canonical DXF analysis path on converted bytes
        # Allow tests to inject a fake analyzer by setting `zuru_ingest.analyze_dxf_bytes`.
        if "analyze_dxf_bytes" in globals():
            analysis = analyze_dxf_bytes(dxf_bytes)
        else:
            import importlib
            analysis = importlib.import_module("zuru_core").analyze_dxf_bytes(dxf_bytes)
        # Attach explicit ingestion provenance without altering evidence records
        analysis = dict(analysis)  # shallow copy to avoid mutating original
        analysis["ingestion_provenance"] = {
            "original_format": "dwg",
            "conversion": "dwg->dxf",
            "converter": os.getenv("DWG_CONVERTER_IMPL") or "injected",
        }
        analysis["converted_dxf_bytes_present"] = False  # do not expose raw bytes by default
        return analysis

    raise ValueError(f"Unsupported file extension: {ext}")
