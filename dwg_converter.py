"""Production LibreDWG-backed DWG -> DXF converter adapter.

This adapter invokes a configured local LibreDWG-compatible executable to
perform DWG->DXF conversion and returns DXF bytes. The implementation
follows strict safety and hygiene rules:

- Uses a dedicated temporary directory for each conversion and removes it
  deterministically on completion.
- Does not perform shell interpolation of filenames; subprocess is invoked
  with an argv list only.
- Enforces a timeout (default 30s) and surfaces subprocess failures as
  exceptions.
- Rejects empty or missing output.
- Validates produced DXF by invoking the canonical DXF analyzer boundary
  (zuru_core.analyze_dxf_bytes) before returning the raw bytes.
- Pins LibreDWG to the immutable commit in libredwg_pin.txt and verifies any
  cached bootstrap binary was built from that same identity before reuse.

Configuration via environment:
- DWG_CONVERTER_EXECUTABLE: path or name of the LibreDWG executable
  (default: 'dwg2dxf').
- DWG_CONVERTER_TIMEOUT: timeout in seconds for the conversion subprocess
  (default: 30).
- RUNNER_TEMP: transient bootstrap/build location.

Note: LibreDWG is GPLv3+; do not assume binary distribution without
reviewing licensing implications.
"""

from __future__ import annotations

import importlib
import os
import pathlib
import shutil
import subprocess
import tempfile
import time


def _read_env_timeout() -> int:
    try:
        return int(os.getenv("DWG_CONVERTER_TIMEOUT", "30"))
    except Exception:
        return 30


def _read_libredwg_pin() -> str:
    pin_file = os.path.join(os.path.dirname(__file__), "libredwg_pin.txt")
    if not os.path.exists(pin_file):
        raise RuntimeError(
            "Missing libredwg_pin.txt pin file in repository root; "
            "a pinned LibreDWG commit SHA is required"
        )
    with open(pin_file, "r", encoding="utf-8") as pf:
        pin = pf.read().strip()
    if len(pin) != 40 or any(ch not in "0123456789abcdefABCDEF" for ch in pin):
        raise RuntimeError("libredwg_pin.txt must contain an exact 40-character commit SHA")
    return pin.lower()


def _read_cached_commit(metadata_path: str) -> str | None:
    if not os.path.exists(metadata_path):
        return None
    try:
        with open(metadata_path, "r", encoding="utf-8") as mf:
            for line in mf:
                key, sep, value = line.partition(":")
                if sep and key.strip() == "upstream_commit":
                    return value.strip().lower()
    except OSError:
        return None
    return None


def _bootstrap_libredwg() -> str:
    """Build pinned LibreDWG in user-space and return the dwg2dxf path.

    A cached binary is reusable only when its recorded upstream commit equals
    the currently reviewed pin. Missing or mismatched cache provenance causes
    the stale cache to be discarded before a fresh pinned build.
    """
    pin = _read_libredwg_pin()
    runner_temp = os.getenv("RUNNER_TEMP") or tempfile.gettempdir()
    build_root = os.path.join(runner_temp, "libredwg-build")
    bin_path = os.path.join(build_root, "bin")
    dwg2dxf_path = os.path.join(bin_path, "dwg2dxf")
    metadata_path = os.path.join(build_root, "build-metadata.txt")

    if os.path.exists(dwg2dxf_path) and os.access(dwg2dxf_path, os.X_OK):
        cached_commit = _read_cached_commit(metadata_path)
        if cached_commit == pin:
            return dwg2dxf_path
        # Never trust an executable whose provenance is absent or does not
        # match the reviewed dependency identity.
        shutil.rmtree(build_root, ignore_errors=True)

    for tool in ("git", "cmake", "ninja", "gcc", "g++"):
        if shutil.which(tool) is None:
            raise RuntimeError(f"Missing build tool required for LibreDWG: {tool}")

    src_dir = os.path.join(runner_temp, f"libredwg-src-{int(time.time())}")

    try:
        subprocess.run(
            ["git", "clone", "--no-checkout", "--depth", "1", "https://github.com/LibreDWG/libredwg.git", src_dir],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=60,
        )
        subprocess.run(
            ["git", "-C", src_dir, "fetch", "--depth", "1", "origin", pin],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=60,
        )
        subprocess.run(
            ["git", "-C", src_dir, "checkout", "--detach", pin],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=30,
        )
    except subprocess.CalledProcessError as ex:
        stderr = (ex.stderr or b"").decode(errors="ignore")
        raise RuntimeError(
            f"Failed to clone/fetch/checkout pinned LibreDWG upstream: {stderr[:500]!r}"
        ) from ex
    except subprocess.TimeoutExpired as ex:
        raise RuntimeError("Pinned LibreDWG source retrieval timed out") from ex

    try:
        commit = subprocess.run(
            ["git", "-C", src_dir, "rev-parse", "HEAD"],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=30,
        ).stdout.decode().strip().lower()
    except Exception as ex:
        raise RuntimeError("Unable to verify resolved LibreDWG source identity") from ex

    if commit != pin:
        raise RuntimeError(
            f"Resolved LibreDWG commit {commit!r} does not match required pinned identity {pin!r}"
        )

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
        subprocess.run(
            cmake_cmd,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=300,
        )
    except subprocess.CalledProcessError as ex:
        out = (ex.stdout or b"").decode(errors="ignore")
        err = (ex.stderr or b"").decode(errors="ignore")
        raise RuntimeError(f"CMake configure failed for LibreDWG: {out[:400]!r}\n{err[:400]!r}") from ex
    except subprocess.TimeoutExpired as ex:
        raise RuntimeError("CMake configure for LibreDWG timed out") from ex

    try:
        subprocess.run(
            ["cmake", "--build", build_dir, "--", "-j", "2"],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=1800,
        )
    except subprocess.CalledProcessError as ex:
        err = (ex.stderr or b"").decode(errors="ignore")
        if "pcre2" in err.lower():
            raise RuntimeError(f"LibreDWG build failed; missing dependency: pcre2; full error: {err[:500]!r}") from ex
        if "iconv" in err.lower() or "libiconv" in err.lower():
            raise RuntimeError(f"LibreDWG build failed; missing dependency: iconv; full error: {err[:500]!r}") from ex
        raise RuntimeError(f"LibreDWG build failed: {err[:500]!r}") from ex
    except subprocess.TimeoutExpired as ex:
        raise RuntimeError("LibreDWG build timed out") from ex

    candidates = [
        os.path.join(build_dir, "dwg2dxf"),
        os.path.join(build_dir, "programs", "dwg2dxf"),
        os.path.join(src_dir, "dwg2dxf"),
    ]
    found = next(
        (c for c in candidates if os.path.exists(c) and os.access(c, os.X_OK)),
        None,
    )
    if not found:
        for p in pathlib.Path(build_dir).rglob("dwg2dxf"):
            if p.is_file() and os.access(str(p), os.X_OK):
                found = str(p)
                break
    if not found:
        raise RuntimeError("LibreDWG built but dwg2dxf executable not found in build output")

    os.makedirs(bin_path, exist_ok=True)
    shutil.copy(found, dwg2dxf_path)
    try:
        os.chmod(dwg2dxf_path, 0o755)
    except Exception:
        pass

    try:
        version_out = subprocess.run(
            [dwg2dxf_path, "--version"],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=10,
        ).stdout.decode().strip()
    except Exception:
        version_out = "(unknown)"

    with open(metadata_path, "w", encoding="utf-8") as mf:
        mf.write(f"upstream_commit: {commit}\n")
        mf.write(f"version_output: {version_out}\n")
        mf.write(f"built_at: {time.ctime()}\n")

    return dwg2dxf_path


def convert_dwg_to_dxf(dwg_bytes: bytes) -> bytes:
    """Convert DWG bytes to DXF bytes using a local LibreDWG executable."""
    if not isinstance(dwg_bytes, (bytes, bytearray)):
        raise TypeError("dwg_bytes must be bytes")

    executable = os.getenv("DWG_CONVERTER_EXECUTABLE", "dwg2dxf")
    timeout = _read_env_timeout()
    tmpdir = tempfile.mkdtemp(prefix="zuru-dwg-conv-")
    in_path = os.path.join(tmpdir, "input.dwg")
    out_path = os.path.join(tmpdir, "output.dxf")

    try:
        with open(in_path, "wb") as f:
            f.write(dwg_bytes)

        def try_style_args(args):
            return subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout)

        try:
            proc = try_style_args([executable, "-o", out_path, in_path])
        except FileNotFoundError:
            executable = _bootstrap_libredwg()
            proc = try_style_args([executable, "-o", out_path, in_path])
        except subprocess.TimeoutExpired as ex:
            raise RuntimeError(f"DWG conversion timed out after {timeout}s") from ex

        if proc.returncode != 0:
            raise RuntimeError(
                f"DWG converter exited non-zero: {proc.returncode}; stderr: {proc.stderr[:500]!r}"
            )
        if not os.path.exists(out_path) or os.path.getsize(out_path) == 0:
            raise RuntimeError("DWG converter produced no DXF output")

        with open(out_path, "rb") as f:
            dxf_bytes = f.read()
        _validate_dxf_bytes(dxf_bytes)
        return dxf_bytes
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def _validate_dxf_bytes(dxf_bytes: bytes) -> None:
    """Validate that DXF bytes are parseable by canonical analyzer."""
    if not isinstance(dxf_bytes, (bytes, bytearray)) or not dxf_bytes:
        raise RuntimeError("DXF bytes are empty")
    analyzer = importlib.import_module("zuru_core").analyze_dxf_bytes
    try:
        analyzer(dxf_bytes)
    except Exception as exc:
        raise RuntimeError(f"DXF validation failed: {exc}") from exc
