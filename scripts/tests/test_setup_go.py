"""Offline installer regression checks using a small SDK fixture."""

import hashlib
import io
import os
from pathlib import Path
import platform
import re
import subprocess
import tarfile
import tempfile
import unittest


@unittest.skipUnless(
    platform.system() == "Linux" and platform.machine() == "x86_64",
    "The local installer targets Linux x86_64",
)
class SetupGoTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="coopace-setup-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.payload = self.root / "fixture.tar.gz"
        binary = b"#!/bin/sh\nprintf 'go version go1.27.3 linux/amd64\\n'\n"
        with tarfile.open(self.payload, "w:gz") as archive:
            info = tarfile.TarInfo("go/bin/go")
            info.size = len(binary)
            info.mode = 0o755
            archive.addfile(info, io.BytesIO(binary))

        source = (Path(__file__).resolve().parents[1] / "setup-go.sh").read_text()
        # Only the isolated fixture copy uses the fixture's real checksum.
        source, replacements = re.subn(
            r"coopace_sha256=[0-9a-f]{64}",
            "coopace_sha256=" + hashlib.sha256(self.payload.read_bytes()).hexdigest(),
            source,
        )
        self.assertEqual(replacements, 1)
        (self.root / "scripts").mkdir()
        (self.root / "scripts/setup-go.sh").write_text(source)
        (self.root / ".go-version").write_text("1.27.3\n")
        self.cached = self.root / ".cache/downloads/go1.27.3.linux-amd64.tar.gz"
        self.installed = self.root / ".local/toolchains/go1.27.3/bin/go"
        self.calls = self.root / "calls.txt"

        (self.root / "bin").mkdir()
        curl = self.root / "bin/curl"
        curl.write_text(r'''#!/usr/bin/env python3
import os
from pathlib import Path
import sys

arguments = sys.argv[1:]
assert arguments[arguments.index("--continue-at") + 1] == "-"
assert "--max-time" not in arguments
output = Path(arguments[arguments.index("--output") + 1])
payload = Path(os.environ["COOPACE_TEST_PAYLOAD"]).read_bytes()
with open(os.environ["COOPACE_TEST_CALLS"], "a") as calls:
    calls.write("download\n")
mode = os.environ["COOPACE_TEST_MODE"]
if mode == "corrupt":
    output.write_bytes(b"corrupted archive")
else:
    offset = output.stat().st_size if output.exists() else 0
    assert output.read_bytes() == payload[:offset] if output.exists() else True
    with output.open("ab") as destination:
        destination.write(payload[offset:offset + 64] if mode == "interrupt" else payload[offset:])
    if mode == "interrupt":
        sys.exit(28)
''')
        curl.chmod(0o755)

    def run_installer(self, mode="complete"):
        environment = dict(os.environ)
        environment.update({
            "PATH": str(self.root / "bin") + os.pathsep + environment["PATH"],
            "COOPACE_TEST_PAYLOAD": str(self.payload),
            "COOPACE_TEST_CALLS": str(self.calls),
            "COOPACE_TEST_MODE": mode,
        })
        return subprocess.run(
            ["sh", "scripts/setup-go.sh"], cwd=self.root, env=environment,
            capture_output=True, text=True, timeout=10,
        )

    def test_interrupted_download_is_preserved_and_resumed(self):
        interrupted = self.run_installer("interrupt")
        self.assertEqual(interrupted.returncode, 28, interrupted.stderr)
        self.assertEqual(self.cached.read_bytes(), self.payload.read_bytes()[:64])
        self.assertFalse(self.installed.exists())

        resumed = self.run_installer()
        self.assertEqual(resumed.returncode, 0, resumed.stderr)
        self.assertEqual(self.cached.read_bytes(), self.payload.read_bytes())
        self.assertTrue(self.installed.is_file())
        self.assertEqual(self.calls.read_text().count("download"), 2)

        already_installed = self.run_installer()
        self.assertEqual(already_installed.returncode, 0, already_installed.stderr)
        self.assertEqual(self.calls.read_text().count("download"), 2)

    def test_verified_cached_archive_installs_without_download(self):
        self.cached.parent.mkdir(parents=True)
        self.cached.write_bytes(self.payload.read_bytes())
        result = self.run_installer()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(self.installed.is_file())
        self.assertFalse(self.calls.exists())

    def test_corrupted_download_is_not_installed(self):
        result = self.run_installer("corrupt")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("checksum mismatch", result.stderr)
        self.assertFalse(self.installed.exists())
        self.assertEqual(self.cached.read_bytes(), b"corrupted archive")


if __name__ == "__main__":
    unittest.main()
