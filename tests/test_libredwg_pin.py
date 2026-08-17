import subprocess
import shutil
import os

from unittest import mock

import dwg_converter


def test_bootstrap_fetches_and_checks_out_pinned_commit(tmp_path, monkeypatch):
    calls = []

    # Ensure required tools appear present
    monkeypatch.setattr(shutil, "which", lambda name: f"/usr/bin/{name}")

    # Provide a predictable RUNNER_TEMP so src_dir path is stable
    monkeypatch.setenv("RUNNER_TEMP", str(tmp_path))

    pin_path = os.path.join(os.path.dirname(dwg_converter.__file__), "libredwg_pin.txt")
    with open(pin_path, "r") as f:
        pin = f.read().strip()

    def fake_run(args, check=False, stdout=None, stderr=None, timeout=None):
        # record the invocation
        calls.append(args)
        # Simulate git rev-parse returning the pinned commit when asked
        if args[:3] == ["git", "-C", mock.ANY] and args[-2:] == ["rev-parse", "HEAD"]:
            return subprocess.CompletedProcess(args, 0, stdout=(pin + "\n").encode(), stderr=b"")
        # Simulate success for clone/fetch/checkout git calls
        if args[0] == "git":
            return subprocess.CompletedProcess(args, 0, stdout=b"", stderr=b"")
        # Simulate cmake configure failing so the bootstrap stops after verification
        if args[0] == "cmake":
            raise subprocess.CalledProcessError(returncode=1, cmd=args, output=b"", stderr=b"cmake not available in test")
        # Default success
        return subprocess.CompletedProcess(args, 0, stdout=b"", stderr=b"")

    monkeypatch.setattr(subprocess, "run", fake_run)

    # Call the bootstrap; it should raise due to cmake mock, but only after
    # clone/fetch/checkout and rev-parse were invoked and verified.
    try:
        dwg_converter._bootstrap_libredwg()
    except RuntimeError as ex:
        # expected because cmake was faked to fail
        pass

    # Ensure git clone (with --no-checkout), fetch of pin and checkout pinned commit were invoked
    flattened = [" ".join(map(str, c)) for c in calls]
    assert any("clone --no-checkout" in s for s in flattened), f"git clone not called: {flattened}"
    assert any(pin in s and "fetch" in s for s in flattened), f"git fetch for pin not called: {flattened}"
    assert any(pin in s and "checkout" in s for s in flattened), f"git checkout for pin not called: {flattened}"
    # Ensure rev-parse was used to read the final commit
    assert any("rev-parse" in s for s in flattened), f"git rev-parse not called: {flattened}"
