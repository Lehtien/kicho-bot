"""Installer invariants with isolated files; API keys never enter real services."""
from contextlib import redirect_stdout
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("desktop_setup", ROOT / "scripts/setup-desktop.py")
setup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(setup)


class SetupTests(unittest.TestCase):
    def test_existing_credentials_are_preserved_without_prompt_or_output(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            target = root / ".env"
            original = "KICHO_PROVIDER=typesafe\nTYPESAFE_API_KEY=secret-existing\nKICHO_MODEL=custom-model\n"
            target.write_text(original, encoding="utf-8")
            alternate = root / "alternate.env"
            alternate.write_text("AI_GATEWAY_API_KEY=secret-alternate", encoding="utf-8")
            output = io.StringIO()
            with patch("builtins.input", side_effect=AssertionError("no prompt")), redirect_stdout(output):
                setup.ensure_credentials(target, [alternate], True)
            self.assertEqual(target.read_text(), original)
            self.assertNotIn("secret-existing", output.getvalue())
            self.assertNotIn("secret-alternate", output.getvalue())

    def test_new_key_is_saved_without_exposing_it(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / ".env"
            output = io.StringIO()
            with patch("builtins.input", return_value="2"), patch.object(setup.sys.stdin, "isatty", return_value=True), \
                    patch.object(setup.getpass, "getpass", return_value="secret-new"), redirect_stdout(output):
                setup.ensure_credentials(path, [], False)
            values = setup.dotenv_values(path)
            self.assertEqual(values["KICHO_PROVIDER"], "typesafe")
            self.assertEqual(values["TYPESAFE_API_KEY"], "secret-new")
            self.assertNotIn("secret-new", output.getvalue())

    def test_noninteractive_missing_key_stops_without_writing_credentials(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / ".env"
            with self.assertRaises(setup.SetupError):
                setup.ensure_credentials(path, [], True)
            self.assertFalse(path.exists())

    def test_versions_preserve_previous_install_and_detect_edits(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "source"
            source.mkdir()
            (source / "SKILL.md").write_text("first", encoding="utf-8")
            first = setup.install_version(source, root / "install")
            self.assertEqual(setup.install_version(source, root / "install"), first)
            (source / "SKILL.md").write_text("second", encoding="utf-8")
            second = setup.install_version(source, root / "install")
            self.assertNotEqual(first, second)
            self.assertEqual((first / "SKILL.md").read_text(), "first")
            (second / "SKILL.md").write_text("user edit", encoding="utf-8")
            with self.assertRaises(setup.SetupError):
                setup.install_version(source, root / "install")
            self.assertEqual((second / "SKILL.md").read_text(), "user edit")

    def test_existing_data_location_is_discovered_and_malformed_config_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            config = root / "desktop.json"
            config.write_text(json.dumps({"mcpServers": {"kicho-bot": {"args": [
                "run", "--env-file", str(root / "old.env"), str(root / "mcp_server.py"),
                "--workspace", str(root / "existing-data")
            ]}}}), encoding="utf-8")
            previous = setup.previous_options(config)
            self.assertEqual(previous["--workspace"], root / "existing-data")
            self.assertEqual(previous["--env-file"], root / "old.env")
            config.write_text("[]", encoding="utf-8")
            with self.assertRaises(setup.SetupError):
                setup.previous_options(config)
            self.assertEqual(config.read_text(), "[]")


if __name__ == "__main__":
    unittest.main()
