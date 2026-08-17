import os
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock

import dwg_converter


class LibreDwgPinTests(unittest.TestCase):
    def setUp(self):
        pin_path = os.path.join(os.path.dirname(dwg_converter.__file__), "libredwg_pin.txt")
        with open(pin_path, "r", encoding="utf-8") as f:
            self.pin = f.read().strip().lower()

    def _fake_run_until_cmake(self, calls):
        def fake_run(args, check=False, stdout=None, stderr=None, timeout=None):
            calls.append(args)
            if args and args[0] == "git" and args[-2:] == ["rev-parse", "HEAD"]:
                return subprocess.CompletedProcess(
                    args, 0, stdout=(self.pin + "\n").encode(), stderr=b""
                )
            if args and args[0] == "git":
                return subprocess.CompletedProcess(args, 0, stdout=b"", stderr=b"")
            if args and args[0] == "cmake":
                raise subprocess.CalledProcessError(
                    returncode=1,
                    cmd=args,
                    output=b"",
                    stderr=b"cmake stopped intentionally by test",
                )
            return subprocess.CompletedProcess(args, 0, stdout=b"", stderr=b"")

        return fake_run

    def test_bootstrap_fetches_checks_out_and_verifies_exact_pinned_commit(self):
        calls = []
        with tempfile.TemporaryDirectory() as tmpdir, \
             mock.patch.dict(os.environ, {"RUNNER_TEMP": tmpdir}, clear=False), \
             mock.patch.object(shutil, "which", side_effect=lambda name: f"/usr/bin/{name}"), \
             mock.patch.object(subprocess, "run", side_effect=self._fake_run_until_cmake(calls)):
            with self.assertRaisesRegex(RuntimeError, "CMake configure failed"):
                dwg_converter._bootstrap_libredwg()

        flattened = [" ".join(map(str, call)) for call in calls]
        self.assertTrue(any("clone --no-checkout" in s for s in flattened), flattened)
        self.assertTrue(any("fetch" in s and self.pin in s for s in flattened), flattened)
        self.assertTrue(any("checkout --detach" in s and self.pin in s for s in flattened), flattened)
        self.assertTrue(any("rev-parse HEAD" in s for s in flattened), flattened)

    def test_matching_cached_binary_is_reused_only_with_matching_provenance(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            build_root = os.path.join(tmpdir, "libredwg-build")
            bin_dir = os.path.join(build_root, "bin")
            os.makedirs(bin_dir)
            binary = os.path.join(bin_dir, "dwg2dxf")
            with open(binary, "wb") as f:
                f.write(b"binary")
            os.chmod(binary, 0o755)
            with open(os.path.join(build_root, "build-metadata.txt"), "w", encoding="utf-8") as f:
                f.write(f"upstream_commit: {self.pin}\n")

            with mock.patch.dict(os.environ, {"RUNNER_TEMP": tmpdir}, clear=False), \
                 mock.patch.object(subprocess, "run") as run_mock:
                resolved = dwg_converter._bootstrap_libredwg()

            self.assertEqual(resolved, binary)
            run_mock.assert_not_called()

    def test_mismatched_cached_binary_is_rejected_before_reuse(self):
        calls = []
        with tempfile.TemporaryDirectory() as tmpdir:
            build_root = os.path.join(tmpdir, "libredwg-build")
            bin_dir = os.path.join(build_root, "bin")
            os.makedirs(bin_dir)
            binary = os.path.join(bin_dir, "dwg2dxf")
            with open(binary, "wb") as f:
                f.write(b"stale-binary")
            os.chmod(binary, 0o755)
            with open(os.path.join(build_root, "build-metadata.txt"), "w", encoding="utf-8") as f:
                f.write("upstream_commit: 0000000000000000000000000000000000000000\n")

            with mock.patch.dict(os.environ, {"RUNNER_TEMP": tmpdir}, clear=False), \
                 mock.patch.object(shutil, "which", side_effect=lambda name: f"/usr/bin/{name}"), \
                 mock.patch.object(subprocess, "run", side_effect=self._fake_run_until_cmake(calls)):
                with self.assertRaisesRegex(RuntimeError, "CMake configure failed"):
                    dwg_converter._bootstrap_libredwg()

            self.assertFalse(os.path.exists(binary))
            flattened = [" ".join(map(str, call)) for call in calls]
            self.assertTrue(any("clone --no-checkout" in s for s in flattened), flattened)


if __name__ == "__main__":
    unittest.main()
