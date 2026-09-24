"""MCP protocol tests use only isolated synthetic receipts and no live API."""
import importlib.util
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
import urllib.error
import urllib.request
from unittest.mock import patch

from mcp import Client, StdioServerParameters

from test_kicho import ROOT, SKILL, classifier, document, mapping, response
from mcp_server import build_server

spec = importlib.util.spec_from_file_location("configure_mcp", ROOT / "scripts/configure-mcp.py")
configuration = importlib.util.module_from_spec(spec)
spec.loader.exec_module(configuration)


def payload(result):
    if result.is_error:
        raise AssertionError(result.content)
    return result.structured_content


class MCPTests(unittest.IsolatedAsyncioTestCase):
    async def test_stdio_discovery_and_dry_run_without_api(self):
        with tempfile.TemporaryDirectory() as temp:
            params = StdioServerParameters(command=sys.executable, args=[
                str(SKILL / "scripts/mcp_server.py"), "--workspace", temp, "--provider", "vercel"
            ], env={"KICHO_PROVIDER": "vercel"})
            async with Client(params, mode="legacy", read_timeout_seconds=15) as client:
                listed = await client.list_tools()
                self.assertEqual({tool.name for tool in listed.tools}, {
                    "get_kicho_guide", "classify_receipt", "list_drafts", "get_draft",
                    "prepare_freee_review", "open_freee_review",
                })
                guide = payload(await client.call_tool("get_kicho_guide"))
                self.assertIn("input_schema", guide)
                self.assertFalse(guide["credential_configured"])
                result = payload(await client.call_tool("classify_receipt", {"document": document(), "dry_run": True}))
                self.assertEqual(result["mode"], "dry-run")
                self.assertEqual(result["provider"], "vercel")
            self.assertFalse(list(Path(temp).rglob("*.json")))

    async def test_classification_persistence_review_and_human_export(self):
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ, {"TYPESAFE_API_KEY": "test-key"}, clear=True), \
                patch.object(classifier, "call_jev", side_effect=lambda request, endpoint, key: response(request)):
            server = build_server(Path(temp), "typesafe")
            async with Client(server) as client:
                classified = payload(await client.call_tool("classify_receipt", {"document": document()}))
                identity = classified["draft_id"]
                self.assertEqual(classified["route"], "candidate_auto")
                self.assertTrue(Path(classified["saved_path"]).is_file())
                self.assertEqual(payload(await client.call_tool("list_drafts", {"client_id": "test-client"}))["total"], 1)
                self.assertEqual(payload(await client.call_tool("get_draft", {"draft_id": identity}))["draft_id"], identity)
                prepared = payload(await client.call_tool("prepare_freee_review", {
                    "draft_ids": [identity], "mapping": mapping().model_dump(),
                }))
                self.assertFalse(prepared["rows"][0]["confirmed"])
                opened = payload(await client.call_tool("open_freee_review", {"client_id": "test-client"}))
                url, token = opened["url"].split("#")
                row = prepared["rows"][0]
                headers = {"Content-Type": "application/json", "X-Kicho-Token": token}
                request = urllib.request.Request(url + "api/confirm", headers=headers, data=json.dumps({
                    "draft_id": identity, "revision": row["revision"]
                }).encode())
                with urllib.request.urlopen(request, timeout=3) as result:
                    self.assertTrue(json.load(result)["ok"])
                with urllib.request.urlopen(urllib.request.Request(url + "api/export", headers=headers, data=b"{}"), timeout=3) as result:
                    batch = json.load(result)
                    self.assertEqual(batch["count"], 1)
                with urllib.request.urlopen(urllib.request.Request(url + "api/exports/" + batch["batch_id"], headers=headers), timeout=3) as result:
                    self.assertTrue(result.read().startswith(b"\xef\xbb\xbf"))
            with self.assertRaises(urllib.error.URLError):
                urllib.request.urlopen(url, timeout=1)
            # Saved drafts remain available after an MCP restart.
            async with Client(build_server(Path(temp), "typesafe")) as client:
                self.assertEqual(payload(await client.call_tool("list_drafts", {"client_id": "test-client"}))["total"], 1)

    async def test_provider_errors_are_redacted_and_no_draft_is_saved(self):
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ, {"TYPESAFE_API_KEY": "private-test-key"}, clear=True), \
                patch.object(classifier, "call_jev", side_effect=urllib.error.HTTPError(
                    "https://api.example.invalid", 403, "private-test-key", {}, io.BytesIO(b"private-test-key")
                )):
            async with Client(build_server(Path(temp), "typesafe")) as client:
                result = await client.call_tool("classify_receipt", {"document": document()})
                self.assertTrue(result.is_error)
                self.assertNotIn("private-test-key", str(result))
            self.assertFalse(list(Path(temp).rglob("*.json")))

    async def test_path_injection_and_cross_client_queue_are_rejected(self):
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ, {"TYPESAFE_API_KEY": "test-key"}, clear=True), \
                patch.object(classifier, "call_jev", side_effect=lambda request, endpoint, key: response(request)):
            async with Client(build_server(Path(temp), "typesafe")) as client:
                invalid = await client.call_tool("get_draft", {"draft_id": "../../.env"})
                self.assertTrue(invalid.is_error)
                classified = payload(await client.call_tool("classify_receipt", {"document": document()}))
                wrong = mapping().model_dump()
                wrong["client_id"] = "another-client"
                result = await client.call_tool("prepare_freee_review", {"draft_ids": [classified["draft_id"]], "mapping": wrong})
                self.assertTrue(result.is_error)
            self.assertFalse(list((Path(temp) / "queues").glob("*.json")))


class ConfigTests(unittest.TestCase):
    def test_registration_preserves_other_settings_and_requires_explicit_replacement(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "claude_desktop_config.json"
            original = {"theme": "dark", "mcpServers": {"existing": {"command": "other-server"}}}
            path.write_text(json.dumps(original), encoding="utf-8")
            config = {"mcpServers": {"kicho-bot": {"command": "uv", "args": ["run"]}}}
            backup = configuration.merge_config(path, config, False)
            self.assertEqual(json.loads(backup.read_text()), original)
            current = json.loads(path.read_text())
            self.assertEqual(current["theme"], "dark")
            self.assertEqual(current["mcpServers"]["existing"], original["mcpServers"]["existing"])
            self.assertIsNone(configuration.merge_config(path, config, False))
            changed = {"mcpServers": {"kicho-bot": {"command": "another-uv"}}}
            with self.assertRaises(ValueError):
                configuration.merge_config(path, changed, False)
            self.assertEqual(json.loads(path.read_text()), current)
            configuration.merge_config(path, changed, True)
            self.assertEqual(json.loads(path.read_text())["mcpServers"]["kicho-bot"], changed["mcpServers"]["kicho-bot"])

    def test_config_points_to_env_file_without_reading_its_secret(self):
        with tempfile.TemporaryDirectory() as temp:
            env = Path(temp) / ".env"
            env.write_text("TYPESAFE_API_KEY=private-test-key", encoding="utf-8")
            config = configuration.make_config(Path(sys.executable), env, Path(temp) / "経理")
            self.assertNotIn("private-test-key", json.dumps(config))
            args = config["mcpServers"]["kicho-bot"]["args"]
            directory = Path(args[args.index("--directory") + 1])
            self.assertEqual(directory / args[args.index("--env-file") + 1], env)


if __name__ == "__main__":
    unittest.main()
