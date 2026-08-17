import os
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock

import zuru_ingest

# Ensure converter module reachable via DWG_CONVERTER_IMPL
os.environ.pop("DWG_CONVERTER_IMPL", None)


class TestRealDwgConverterAdapter(unittest.TestCase):
    def setUp(self):
        # Make sure tests use our production adapter by setting the env var
        os.environ["DWG_CONVERTER_IMPL"] = "dwg_converter"
        # Inject a fake zuru_core module to avoid importing ezdxf during tests
        import types, sys
        fake_mod = types.ModuleType("zuru_core")
        def fake_analyze(b):
            return {}
        fake_mod.analyze_dxf_bytes = fake_analyze
        sys.modules["zuru_core"] = fake_mod
        # Patch the analyzer attribute in case other import paths are used
        self.analyzer_patcher = mock.patch("zuru_core.analyze_dxf_bytes", side_effect=fake_analyze)
        self.analyzer_patcher.start()

    def tearDown(self):
        os.environ.pop("DWG_CONVERTER_IMPL", None)
        self.analyzer_patcher.stop()

    def test_executable_unavailable_raises(self):
        # subprocess.run raises FileNotFoundError when exec missing
        with mock.patch("subprocess.run", side_effect=FileNotFoundError()):
            with self.assertRaises(zuru_ingest.DwgConversionError):
                zuru_ingest.ingest_file_bytes("file.dwg", b"data")

    def test_subprocess_non_zero_exit_raises(self):
        def fake_run_nonzero(*args, **kwargs):
            # simulate non-zero exit for first attempt
            return subprocess.CompletedProcess(args=kwargs.get("args", args), returncode=2, stdout=b"", stderr=b"err")

        with mock.patch("subprocess.run", side_effect=fake_run_nonzero):
            with self.assertRaises(zuru_ingest.DwgConversionError):
                zuru_ingest.ingest_file_bytes("file.dwg", b"data")

    def test_timeout_raises(self):
        with mock.patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="dwg2dxf", timeout=1)):
            with self.assertRaises(zuru_ingest.DwgConversionError):
                zuru_ingest.ingest_file_bytes("file.dwg", b"data")

    def test_empty_output_raises(self):
        # Simulate subprocess returning success but producing no stdout and no output file
        def fake_run_empty(args, stdout, stderr, timeout):
            return subprocess.CompletedProcess(args=args, returncode=0, stdout=b"", stderr=b"")

        with mock.patch("subprocess.run", side_effect=fake_run_empty):
            with self.assertRaises(zuru_ingest.DwgConversionError):
                zuru_ingest.ingest_file_bytes("file.dwg", b"data")

    def test_successful_conversion_writes_and_cleans_tmpdir(self):
        # Use a stable temporary directory created by the test so cleanup can be asserted
        base_tmp = tempfile.mkdtemp(prefix="test-zuru-dwg-")

        def mkdtemp_override(prefix):
            path = os.path.join(base_tmp, "workdir")
            os.makedirs(path, exist_ok=True)
            return path

        # Prepare fake run that writes output file when called in dwg2dxf style
        def fake_run_write(args, stdout, stderr, timeout):
            # args expected: [executable, in_path, out_path]
            if len(args) >= 3:
                out_path = args[2]
                with open(out_path, "wb") as f:
                    f.write(b"DXF_CONTENT_FROM_DWG")
                return subprocess.CompletedProcess(args=args, returncode=0, stdout=b"", stderr=b"")
            # fallback style: write to stdout
            return subprocess.CompletedProcess(args=args, returncode=0, stdout=b"DXF_CONTENT_FROM_DWG", stderr=b"")

        with mock.patch("tempfile.mkdtemp", side_effect=mkdtemp_override):
            with mock.patch("subprocess.run", side_effect=fake_run_write):
                result = zuru_ingest.ingest_file_bytes("file.dwg", b"dummydwg")
                # Should have ingestion provenance added
                self.assertIn("ingestion_provenance", result)

        # Assert the test-created base_tmp/workdir was removed by the adapter
        self.assertFalse(os.path.exists(os.path.join(base_tmp, "workdir")))

        # Clean up base_tmp
        try:
            shutil.rmtree(base_tmp)
        except Exception:
            pass


if __name__ == "__main__":
    unittest.main()
