"""Exercise the Mac launcher on POSIX with isolated OS/download boundaries."""
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipIf(os.name == "nt", "POSIX shell launcher")
class MacSetupTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.bin = self.root / "bin"
        self.bin.mkdir()
        for command in ("dirname", "mkdir", "mktemp", "rm", "tar", "gzip", "cp", "chmod", "shasum"):
            location = shutil.which(command)
            if not location:
                self.skipTest(f"{command} is required")
            (self.bin / command).symlink_to(location)
        self.stub("uname", "import os, sys\nprint(os.environ['TEST_OS'] if sys.argv[1] == '-s' else os.environ['TEST_ARCH'])\n")
        self.env = {**os.environ, "PATH": str(self.bin), "TEST_OS": "Darwin", "TEST_ARCH": "arm64",
                    "TEST_ARGS": str(self.root / "args.json"), "TEST_FIXTURE": str(self.root / "asset.tar.gz"),
                    "TEST_URLS": str(self.root / "urls.txt"), "TMPDIR": str(self.root)}
        self.install = self.root / "Application Support" / "kicho-bot"

    def stub(self, name, body):
        path = self.bin / name
        path.write_text(f"#!{sys.executable}\n{body}", encoding="utf-8")
        path.chmod(0o700)

    def uv_bytes(self):
        return (f"#!{sys.executable}\nimport json, os, pathlib, sys\n"
                "pathlib.Path(os.environ['TEST_ARGS']).write_text(json.dumps(sys.argv[1:]))\n").encode()

    def run_launcher(self, *args):
        return subprocess.run(["/bin/bash", str(ROOT / "setup.command"), "--install-root", str(self.install), *args],
                              env=self.env, capture_output=True, text=True, encoding="utf-8", timeout=30)

    def prepare_download(self, arch):
        target = f"uv-{arch}-apple-darwin"
        with tarfile.open(self.root / "asset.tar.gz", "w:gz") as archive:
            binary = self.uv_bytes()
            info = tarfile.TarInfo(f"{target}/uv")
            info.size = len(binary)
            info.mode = 0o700
            archive.addfile(info, io.BytesIO(binary))
        self.stub("curl", """import hashlib, os, pathlib, shutil, sys
url = next(arg for arg in sys.argv if arg.startswith('https://'))
with open(os.environ['TEST_URLS'], 'a') as output:
    output.write(url + '\\n')
destination = pathlib.Path(sys.argv[sys.argv.index('-o') + 1])
source = pathlib.Path(os.environ['TEST_FIXTURE'])
if url.endswith('.sha256'):
    digest = '0' * 64 if os.environ.get('TEST_BAD_HASH') else hashlib.sha256(source.read_bytes()).hexdigest()
    destination.write_text(digest + '  asset.tar.gz\\n')
else:
    shutil.copyfile(source, destination)
""")

    def test_existing_uv_and_paths_with_spaces_are_preserved(self):
        (self.bin / "uv").write_bytes(self.uv_bytes())
        (self.bin / "uv").chmod(0o700)
        config = str(self.root / "Claude settings.json")
        result = self.run_launcher("--config", config, "--non-interactive")
        self.assertEqual(result.returncode, 0, result.stderr)
        args = json.loads((self.root / "args.json").read_text())
        self.assertEqual(args[args.index("--config") + 1], config)
        self.assertEqual(args[args.index("--install-root") + 1], str(self.install))
        self.assertIn("--non-interactive", args)
        self.assertFalse((self.root / "urls.txt").exists())

    def test_downloads_correct_architecture_and_reuses_verified_runtime(self):
        for machine, arch in [("arm64", "aarch64"), ("x86_64", "x86_64")]:
            with self.subTest(machine=machine):
                self.env["TEST_ARCH"] = machine
                self.prepare_download(arch)
                result = self.run_launcher()
                self.assertEqual(result.returncode, 0, result.stderr)
                runtime = self.install / "runtime" / f"uv-0.12.5-{arch}-apple-darwin" / "uv"
                self.assertEqual(runtime.read_bytes(), self.uv_bytes())
                urls = (self.root / "urls.txt").read_text()
                self.assertIn(f"uv-{arch}-apple-darwin.tar.gz.sha256", urls)
                self.assertEqual(self.run_launcher().returncode, 0)
                self.assertEqual((self.root / "urls.txt").read_text(), urls)
                self.assertFalse(list(self.root.glob("kicho-uv.*")))

    def test_checksum_mismatch_does_not_install_or_execute(self):
        self.prepare_download("aarch64")
        self.env["TEST_BAD_HASH"] = "1"
        result = self.run_launcher()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("検証に失敗", result.stderr)
        self.assertFalse((self.install / "runtime").exists())
        self.assertFalse((self.root / "args.json").exists())
        self.assertFalse(list(self.root.glob("kicho-uv.*")))

    def test_other_os_is_rejected_before_installation(self):
        self.env["TEST_OS"] = "Linux"
        result = self.run_launcher()
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.install.exists())


if __name__ == "__main__":
    unittest.main()
