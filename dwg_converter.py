"""Production LibreDWG-backed DWG -> DXF converter adapter.

This adapter invokes a configured local LibreDWG-compatible executable to
perform DWG->DXF conversion and returns DXF bytes. The implementation
follows strict safety and hygiene rules:

- Uses a dedicated temporary directory for each conversion and removes it
  deterministically on completion.
- Does not perform shell interpolation of filenames; subprocess is invoked
  with an argv list only.
- Enforces a timeout (default 30s) and surface subprocess failures as
  exceptions.
- Rejects empty or missing output.
- Validates produced DXF by invoking the canonical DXF analyzer boundary
  (zuru_core.analyze_dxf_bytes) before returning the raw bytes.

Configuration via environment:
- DWG_CONVERTER_EXECUTABLE: path or name of the LibreDWG executable
  (default: 'dwg2dxf'). The adapter will try both 'dwg2dxf input output'
  and 'dwgread -O DXF input' styles as fallbacks when appropriate.
- DWG_CONVERTER_TIMEOUT: timeout in seconds for the conversion subprocess
  (default: 30).

Note: LibreDWG is GPLv3+; do not assume binary distribution without
reviewing licensing implications.
"""

from __future__ import annotations

import importlib
import os
import shutil
import subprocess
import tempfile
from typing import Optional


def _read_env_timeout() -> int:
    try:
        return int(os.getenv("DWG_CONVERTER_TIMEOUT", "30"))
    except Exception:
        return 30


def convert_dwg_to_dxf(dwg_bytes: bytes) -> bytes:
    """Convert DWG bytes to DXF bytes using a local LibreDWG executable.

    Raises RuntimeError on failure. Returns raw DXF bytes on success.
    """
    if not isinstance(dwg_bytes, (bytes, bytearray)):
        raise TypeError("dwg_bytes must be bytes")

    executable = os.getenv("DWG_CONVERTER_EXECUTABLE", "dwg2dxf")
    timeout = _read_env_timeout()

    tmpdir = tempfile.mkdtemp(prefix="zuru-dwg-conv-")
    in_path = os.path.join(tmpdir, "input.dwg")
    out_path = os.path.join(tmpdir, "output.dxf")

    try:
        # Write input DWG bytes
        with open(in_path, "wb") as f:
            f.write(dwg_bytes)

        # Attempt style 1: dwg2dxf input output
        try:
            proc = subprocess.run([executable, in_path, out_path], stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout)
            if proc.returncode == 0 and os.path.exists(out_path) and os.path.getsize(out_path) > 0:
                with open(out_path, "rb") as f:
                    dxf_bytes = f.read()
                # Validate DXF using canonical analyzer
                _validate_dxf_bytes(dxf_bytes)
                return dxf_bytes
            # If executable returned non-zero or output missing/empty, fallthrough to style 2
        except FileNotFoundError:
            # Executable not found — raise a clear error
            raise RuntimeError(f"LibreDWG executable not found: {executable}")
        except subprocess.TimeoutExpired as ex:
            raise RuntimeError(f"DWG conversion timed out after {timeout}s")
        except subprocess.CalledProcessError as ex:
            # treat as conversion failure
            raise RuntimeError(f"DWG converter failed: {ex}")

        # Attempt style 2: dwgread -O DXF input  (emit DXF to stdout)
        try:
            proc2 = subprocess.run([executable, "-O", "DXF", in_path], stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout)
            if proc2.returncode != 0:
                raise RuntimeError(f"DWG converter exited non-zero: {proc2.returncode}; stderr: {proc2.stderr[:200]!r}")
            if not proc2.stdout:
                raise RuntimeError("DWG converter produced empty DXF output")
            dxf_bytes = proc2.stdout
            _validate_dxf_bytes(dxf_bytes)
            return dxf_bytes
        except FileNotFoundError:
            raise RuntimeError(f"LibreDWG executable not found: {executable}")
        except subprocess.TimeoutExpired:
            raise RuntimeError(f"DWG conversion timed out after {timeout}s")

        # If both strategies failed to yield output, raise
        raise RuntimeError("DWG conversion produced no DXF output")
    finally:
        # Clean up temporary directory deterministically
        try:
            shutil.rmtree(tmpdir)
        except Exception:
            # Best-effort cleanup — do not mask earlier exceptions
            pass


def _validate_dxf_bytes(dxf_bytes: bytes) -> None:
    """Validate that DXF bytes are parseable by canonical analyzer.

    Imports the canonical analyzer at runtime to avoid heavy imports at
    module import time and to allow tests to monkeypatch the analyzer.
    """
    if not isinstance(dxf_bytes, (bytes, bytearray)) or len(dxf_bytes) == 0:
        raise RuntimeError("DXF bytes are empty")

    # Use the canonical analyzer as the validation boundary. Tests can patch
    # zuru_core.analyze_dxf_bytes or set an injected analyzer to control
    # behavior during unit tests.
    analyzer = importlib.import_module("zuru_core").analyze_dxf_bytes
    # Analyzer may raise on invalid DXF; propagate that as a RuntimeError
    try:
        analyzer(dxf_bytes)
    except Exception as exc:
        raise RuntimeError(f"DXF validation failed: {exc}")
