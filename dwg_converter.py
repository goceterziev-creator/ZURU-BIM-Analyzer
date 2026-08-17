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

Behavioral extension for the test/runtime environment:
- If the configured LibreDWG executable is not found in PATH, attempt a
  user-space build of LibreDWG from the official upstream via cmake+ninja
  into the runner temp directory. This build runs without sudo and only
  uses tools expected to be present on CI (git, cmake, ninja, gcc).
- On build failure due to a missing tool/dependency, raise a clear error
  naming the missing dependency so the runner state can be preserved.

Configuration via environment:
- DWG_CONVERTER_EXECUTABLE: path or name of the LibreDWG executable
  (default: 'dwg2dxf'). The adapter will try both 'dwg2dxf input output'
  and 'dwgread -O DXF input' styles as fallbacks when appropriate.
- DWG_CONVERTER_TIMEOUT: timeout in seconds for the conversion subprocess
  (default: 30).
- RUNNER_TEMP (used to store transient build artifacts)

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

# tooling
import pathlib
import time


def _read_env_timeout() -> int:
    try:
        return int(os.getenv("DWG_CONVERTER_TIMEOUT", "30"))
    except Exception:
        return 30


def _bootstrap_libredwg() -> str:
    """Attempt to build LibreDWG in user-space and return path to dwg2dxf.

    The build is placed under RUNNER_TEMP/libredwg-build to reuse between
    invocations. If a build already exists, it will be reused.

    Raises RuntimeError describing the earliest missing dependency or
    build failure.
    """
    runner_temp = os.getenv("RUNNER_TEMP") or tempfile.gettempdir()
    build_root = os.path.join(runner_temp, "libredwg-build")
    bin_path = os.path.join(build_root, "bin")
    dwg2dxf_path = os.path.join(bin_path, "dwg2dxf")

    # If already built, return cached path
    if os.path.exists(dwg2dxf_path) and os.access(dwg2dxf_path, os.X_OK):
        return dwg2dxf_path

    # Ensure required host tools are present
    for tool in ("git", "cmake", "ninja", "gcc", "g++"):
        if shutil.which(tool) is None:
            raise RuntimeError(f"Missing build tool required for LibreDWG: {tool}")

    # Clone into a fresh source dir
    src_dir = os.path.join(runner_temp, f"libredwg-src-{int(time.time())}")

    # Enforce pinned identity: a file at repository root must contain the
    # immutable commit SHA to fetch. This prevents silent upstream drift.
    repo_root = os.path.dirname(__file__)
    pin_file = os.path.join(repo_root, "libredwg_pin.txt")
    if not os.path.exists(pin_file):
        raise RuntimeError("Missing libredwg_pin.txt pin file in repository root; a pinned LibreDWG commit SHA is required")
    with open(pin_file, "r") as pf:
        pin = pf.read().strip()
    if not pin or len(pin) < 7:
        raise RuntimeError("libredwg_pin.txt does not contain a valid commit SHA")

    try:
        # Clone without checking out to minimize transient default-branch trust
        subprocess.run(["git", "clone", "--no-checkout", "--depth", "1", "https://github.com/LibreDWG/libredwg.git", src_dir], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        # Fetch the exact pinned commit and detach-checkout it. This guarantees
        # the source used for build matches the reviewed immutable identity.
        subprocess.run(["git", "-C", src_dir, "fetch", "--depth", "1", "origin", pin], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60)
        subprocess.run(["git", "-C", src_dir, "checkout", "--detach", pin], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30)
    except subprocess.CalledProcessError as ex:
        raise RuntimeError(f"Failed to clone/fetch/checkout pinned LibreDWG upstream: {ex.stderr.decode(errors='ignore')[:500]!r}")

    # Determine upstream commit for provenance and verify it equals the pin
    try:
        commit = subprocess.run(["git", "-C", src_dir, "rev-parse", "HEAD"], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30).stdout.decode().strip()
    except Exception:
        commit = "unknown"
    if commit != pin:
        raise RuntimeError(f"Resolved LibreDWG commit {commit!r} does not match required pinned identity {pin!r}")

    # Configure minimal cmake build (disable JSON to reduce deps)
    build_dir = os.path.join(src_dir, "build")
    os.makedirs(build_dir, exist_ok=True)
    cmake_cmd = [
        "cmake",
        "-S", src_dir,
        "-B", build_dir,
        "-G", "Ninja",
        "-DLIBREDWG_DISABLE_JSON=ON",
        "-DCMAKE_BUILD_TYPE=Release",
    ]
    try:
        proc_cfg = subprocess.run(cmake_cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=300)
    except subprocess.CalledProcessError as ex:
        out = (ex.stdout or b"").decode(errors="ignore")
        err = (ex.stderr or b"").decode(errors="ignore")
        raise RuntimeError(f"CMake configure failed for LibreDWG: {out[:400]!r}\n{err[:400]!r}")
    except subprocess.TimeoutExpired:
        raise RuntimeError("CMake configure for LibreDWG timed out")

    # Build with ninja
    try:
        proc_build = subprocess.run(["cmake", "--build", build_dir, "--", "-j", "2"], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=1800)
    except subprocess.CalledProcessError as ex:
        out = (ex.stdout or b"").decode(errors="ignore")
        err = (ex.stderr or b"").decode(errors="ignore")
        # Try to detect missing dependency names in stderr
        if "pcre2" in err.lower():
            missing = "pcre2"
        elif "iconv" in err.lower() or "libiconv" in err.lower():
            missing = "iconv"
        else:
            missing = None
        if missing:
            raise RuntimeError(f"LibreDWG build failed; missing dependency: {missing}; full error: {err[:500]!r}")
        raise RuntimeError(f"LibreDWG build failed: {err[:500]!r}")
    except subprocess.TimeoutExpired:
        raise RuntimeError("LibreDWG build timed out")

    # Locate built executable(s)
    candidates = [
        os.path.join(build_dir, "dwg2dxf"),
        os.path.join(build_dir, "programs", "dwg2dxf"),
        os.path.join(src_dir, "dwg2dxf"),
    ]
    found = None
    for c in candidates:
        if os.path.exists(c) and os.access(c, os.X_OK):
            found = c
            break

    if not found:
        # As a fallback, search build dir
        for p in pathlib.Path(build_dir).rglob("dwg2dxf"):
            if p.is_file() and os.access(str(p), os.X_OK):
                found = str(p)
                break

    if not found:
        raise RuntimeError("LibreDWG built but dwg2dxf executable not found in build output")

    # Prepare final bin dir
    os.makedirs(bin_path, exist_ok=True)
    shutil.copy(found, dwg2dxf_path)
    try:
        os.chmod(dwg2dxf_path, 0o755)
    except Exception:
        pass

    # Record version/provenance for debugging by writing a small metadata file
    try:
        version_out = subprocess.run([dwg2dxf_path, "--version"], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10).stdout.decode().strip()
    except Exception:
        version_out = "(unknown)"
    meta = {
        "upstream_commit": commit,
        "version_output": version_out,
        "built_at": time.ctime(),
    }
    try:
        with open(os.path.join(build_root, "build-metadata.txt"), "w") as mf:
            for k, v in meta.items():
                mf.write(f"{k}: {v}\n")
    except Exception:
        pass

    return dwg2dxf_path


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

        # Helper to attempt conversion styles
        def try_style_args(args):
            proc = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout)
            return proc

        # Attempt style 1: dwg2dxf input output
        try:
            proc = try_style_args([executable, in_path, out_path])
            if proc.returncode == 0 and os.path.exists(out_path) and os.path.getsize(out_path) > 0:
                with open(out_path, "rb") as f:
                    dxf_bytes = f.read()
                # Validate DXF using canonical analyzer
                _validate_dxf_bytes(dxf_bytes)
                return dxf_bytes
            # If executable returned non-zero or output missing/empty, fallthrough to style 2
        except FileNotFoundError:
            # Attempt bootstrap and retry once
            built = _bootstrap_libredwg()
            # override executable for this run only
            executable = built
            # retry style 1
            try:
                proc = try_style_args([executable, in_path, out_path])
                if proc.returncode == 0 and os.path.exists(out_path) and os.path.getsize(out_path) > 0:
                    with open(out_path, "rb") as f:
                        dxf_bytes = f.read()
                    _validate_dxf_bytes(dxf_bytes)
                    return dxf_bytes
            except Exception as ex:
                raise RuntimeError(f"DWG conversion failed after bootstrap: {ex}")
        except subprocess.TimeoutExpired:
            raise RuntimeError(f"DWG conversion timed out after {timeout}s")
        except subprocess.CalledProcessError as ex:
            # treat as conversion failure
            raise RuntimeError(f"DWG converter failed: {ex}")

        # Attempt style 2: dwgread -O DXF input  (emit DXF to stdout)
        try:
            proc2 = try_style_args([executable, "-O", "DXF", in_path])
            if proc2.returncode != 0:
                raise RuntimeError(f"DWG converter exited non-zero: {proc2.returncode}; stderr: {proc2.stderr[:200]!r}")
            if not proc2.stdout:
                raise RuntimeError("DWG converter produced empty DXF output")
            dxf_bytes = proc2.stdout
            _validate_dxf_bytes(dxf_bytes)
            return dxf_bytes
        except FileNotFoundError:
            # Try bootstrap once more
            built = _bootstrap_libredwg()
            proc2 = try_style_args([built, "-O", "DXF", in_path])
            if proc2.returncode != 0:
                raise RuntimeError(f"DWG converter exited non-zero after build: {proc2.returncode}; stderr: {proc2.stderr[:500]!r}")
            if not proc2.stdout:
                raise RuntimeError("DWG converter produced empty DXF output after build")
            dxf_bytes = proc2.stdout
            _validate_dxf_bytes(dxf_bytes)
            return dxf_bytes
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
