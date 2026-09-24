"""Cross-platform behavior with real files, subprocesses and Japanese paths."""
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from contextlib import redirect_stderr

from test_kicho import ROOT, SKILL, classifier, draft, mapping
from freee_deals import load_queue
from queue_store import queue_lock

spec = importlib.util.spec_from_file_location("installer", ROOT / "scripts/install-skills.py")
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)


class InstallationTests(unittest.TestCase):
    def test_copies_update_and_preserve_local_changes(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "元 スキル"
            source.mkdir()
            (source / "SKILL.md").write_text("first", encoding="utf-8")
            targets = installer.install(source, root, "both", mode="copy")
            self.assertTrue(all(not p.is_symlink() for p in targets))
            self.assertEqual(installer.install(source, root, "both", mode="copy"), targets)
            (source / "SKILL.md").write_text("updated", encoding="utf-8")
            installer.install(source, root, "both", mode="copy")
            self.assertTrue(all((p / "SKILL.md").read_text(encoding="utf-8") == "updated" for p in targets))
            (targets[1] / "SKILL.md").write_text("user edit", encoding="utf-8")
            (source / "SKILL.md").write_text("third", encoding="utf-8")
            with self.assertRaises(ValueError):
                installer.install(source, root, "both", mode="copy")
            self.assertEqual((targets[0] / "SKILL.md").read_text(encoding="utf-8"), "updated")
            self.assertEqual((targets[1] / "SKILL.md").read_text(encoding="utf-8"), "user edit")

    def test_unmanaged_directory_is_preserved(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            existing = root / ".claude/skills/kicho-bot"
            existing.mkdir(parents=True)
            (existing / "SKILL.md").write_text("user skill", encoding="utf-8")
            with self.assertRaises(ValueError):
                installer.install(SKILL, root, "both", mode="copy")
            self.assertFalse((root / ".agents/skills/kicho-bot").exists())
            self.assertEqual((existing / "SKILL.md").read_text(encoding="utf-8"), "user skill")

    def test_default_registration_and_repeated_install(self):
        with tempfile.TemporaryDirectory() as temp:
            targets = installer.install(SKILL, Path(temp), "both")
            self.assertTrue(all((p / "SKILL.md").is_file() for p in targets))
            self.assertTrue(all(p.is_symlink() == (os.name != "nt") for p in targets))
            self.assertEqual(installer.install(SKILL, Path(temp), "both"), targets)


class PortabilityTests(unittest.TestCase):
    def test_json_file_output_is_utf8_even_with_legacy_console_encoding(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "領収書 日本語.json"
            result = subprocess.run([sys.executable, str(SKILL / "scripts/classify_journal.py"),
                                     str(SKILL / "assets/sample-extracted.json"), "--provider", "vercel",
                                     "--dry-run", "--out", str(output)],
                                    env={**os.environ, "PYTHONIOENCODING": "cp932"},
                                    capture_output=True, check=True)
            self.assertEqual(result.stdout, b"")
            data = json.loads(output.read_bytes().decode("utf-8"))
            self.assertEqual(data["mode"], "dry-run")
            self.assertIn("消耗品費", output.read_text(encoding="utf-8"))

    def test_failed_classification_preserves_previous_output(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "draft.json"
            output.write_text("previous", encoding="utf-8")
            with redirect_stderr(io.StringIO()), patch.dict(os.environ, {}, clear=True), patch.object(sys, "argv", [
                "classify", str(SKILL / "assets/sample-extracted.json"), "--out", str(output)
            ]):
                self.assertEqual(classifier.main(), 2)
            self.assertEqual(output.read_text(encoding="utf-8"), "previous")

    def test_quoted_glob_and_bom_mapping_create_queue(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "経理 データ"
            root.mkdir()
            (root / "draft-001.json").write_text(draft().model_dump_json(), encoding="utf-8-sig")
            (root / "mapping.json").write_text(mapping().model_dump_json(), encoding="utf-8-sig")
            output = root / "queue.json"
            command = [sys.executable, str(SKILL / "scripts/freee_deals.py"), str(root / "draft-*.json"),
                       "--mapping", str(root / "mapping.json"), "--out", str(output)]
            subprocess.run(command, capture_output=True, check=True)
            self.assertEqual(len(load_queue(output).drafts), 1)
            command[2] = str(root / "missing-*.json")
            self.assertNotEqual(subprocess.run(command, capture_output=True).returncode, 0)
            self.assertEqual(len(load_queue(output).drafts), 1)

    def test_lock_serializes_processes_and_releases_on_exception(self):
        code = '''
import sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from queue_store import queue_lock
print("ready", flush=True)
with queue_lock(Path(sys.argv[2])):
    print("acquired", flush=True)
'''
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "確認 キュー.json"
            child = None
            try:
                with self.assertRaisesRegex(ValueError, "test release"):
                    with queue_lock(path):
                        child = subprocess.Popen([sys.executable, "-c", code, str(SKILL / "scripts"), str(path)],
                                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                        self.assertEqual(child.stdout.readline().strip(), "ready")
                        with self.assertRaises(subprocess.TimeoutExpired):
                            child.wait(timeout=0.3)
                        raise ValueError("test release")
                stdout, stderr = child.communicate(timeout=5)
                self.assertEqual(child.returncode, 0, stderr)
                self.assertEqual(stdout.strip(), "acquired")
            finally:
                if child is not None and child.poll() is None:
                    child.kill()
                    child.communicate()
