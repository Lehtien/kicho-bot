#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["mcp>=2.2,<3", "python-dotenv>=1.2,<2", "pydantic>=2.12,<3"]
# ///
"""One-time Desktop setup with private key input and an actual MCP connection check."""
from __future__ import annotations

import argparse
import asyncio
import getpass
import hashlib
import importlib.util
import json
import os
import shlex
from pathlib import Path
import subprocess
import sys
import tempfile

from dotenv import dotenv_values, set_key
from mcp import StdioServerParameters

ROOT = Path(__file__).resolve().parents[1]
EXPECTED_TOOLS = {"get_kicho_guide", "classify_receipt", "list_drafts", "get_draft",
                  "prepare_freee_review", "open_freee_review"}


def module_from_file(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


configuration = module_from_file("kicho_configuration", "configure-mcp.py")
installation = module_from_file("kicho_installation", "install-skills.py")


class SetupError(Exception):
    pass


def previous_options(config_path: Path) -> dict[str, Path]:
    if not config_path.exists():
        return {}
    try:
        current = json.loads(config_path.read_text(encoding="utf-8-sig"))
        servers = current.get("mcpServers", {})
        entry = servers.get("kicho-bot", {})
        args = entry.get("args", [])
        if not isinstance(args, list) or any(not isinstance(arg, str) for arg in args):
            raise ValueError("invalid arguments")
        result = {}
        # Only migrate paths from this project's existing local server.
        if not any(Path(arg).name == "mcp_server.py" for arg in args):
            return result
        for flag in ("--env-file", "--workspace"):
            if flag in args:
                index = args.index(flag) + 1
                if index < len(args):
                    value = args[index]
                    if flag == "--env-file" and value.startswith(("'", '"')):
                        paths = shlex.split(value)
                        if len(paths) != 1:
                            raise ValueError("ambiguous environment file")
                        value = paths[0]
                    if Path(value).is_absolute():
                        result[flag] = Path(value)
                    elif flag == "--env-file" and "--directory" in args:
                        directory = args[args.index("--directory") + 1]
                        if Path(directory).is_absolute():
                            result[flag] = Path(directory) / value
        return result
    except (AttributeError, TypeError, ValueError):
        raise SetupError("既存のClaude Desktop設定を読み取れません。元の設定は上書きしていません。") from None


def install_version(source: Path, install_root: Path) -> Path:
    files = installation.fingerprints(source)
    identity = hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest()[:24]
    destination = install_root / "versions" / identity
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        if installation.fingerprints(destination) != files:
            raise SetupError("インストール済みの本体に変更があります。変更を退避してから再実行してください。")
    else:
        installation.install_copy(source, destination, files)
    return destination


def selected_provider(values: dict) -> str | None:
    selected = values.get("KICHO_PROVIDER")
    keys = {"vercel": "AI_GATEWAY_API_KEY", "typesafe": "TYPESAFE_API_KEY"}
    if selected in keys and values.get(keys[selected]):
        return selected
    if not selected:
        available = [name for name, key in keys.items() if values.get(key)]
        if len(available) == 1:
            return available[0]
    return None


def ensure_credentials(target: Path, candidates: list[Path], non_interactive: bool) -> None:
    if not target.exists():
        source = next((path for path in candidates if path.is_file()), None)
        if source:
            with target.open("xb") as output:
                output.write(source.read_bytes())
            if os.name != "nt":
                target.chmod(0o600)
    values = dotenv_values(target, encoding="utf-8-sig") if target.exists() else {}
    if selected_provider(values):
        print("保存済みのAPI設定を使用します。キーは表示しません。", flush=True)
        return
    if non_interactive:
        raise SetupError("APIキーの入力が必要です。Windowsではsetup.cmd、Macではsetup.commandを自分で開いて入力してください。")
    print("接続先を選んでください: 1 = Vercel AI Gateway / 2 = Jev公式", flush=True)
    answer = input("番号 [1]: ").strip() or "1"
    if answer not in ("1", "2"):
        raise SetupError("1または2を選んで、もう一度実行してください。")
    provider = "vercel" if answer == "1" else "typesafe"
    key_name = "AI_GATEWAY_API_KEY" if provider == "vercel" else "TYPESAFE_API_KEY"
    # Refuse non-console input instead of getpass falling back to visible input.
    if not sys.stdin.isatty():
        raise SetupError("キーはチャットへ渡さず、セットアップを開いたターミナルへ入力してください。")
    key = getpass.getpass("APIキー（入力内容は表示されません）: ").strip()
    if not key or any(character in key for character in ("\n", "\r", "\x00")):
        raise SetupError("APIキーが空欄か、改行を含んでいます。もう一度入力してください。")
    descriptor, temporary = tempfile.mkstemp(prefix=".kicho-key-", dir=target.parent)
    os.close(descriptor)
    try:
        temp_path = Path(temporary)
        if target.exists():
            temp_path.write_text(target.read_text(encoding="utf-8-sig"), encoding="utf-8")
        set_key(str(temp_path), "KICHO_PROVIDER", provider)
        set_key(str(temp_path), key_name, key)
        # A model override from a different provider must not survive a switch.
        if values.get("KICHO_PROVIDER") != provider and values.get("KICHO_MODEL"):
            set_key(str(temp_path), "KICHO_MODEL", "")
        os.replace(temp_path, target)
    finally:
        key = ""
        if os.path.exists(temporary):
            os.unlink(temporary)


async def verify_connection(config: dict) -> None:
    entry = config["mcpServers"]["kicho-bot"]
    # Preserve explicitly configured uv runtime/cache locations, including isolated tests.
    runtime_env = {key: value for key, value in os.environ.items() if key.startswith("UV_")}
    params = StdioServerParameters(command=entry["command"], args=entry["args"], env=runtime_env)
    with tempfile.TemporaryFile(mode="w+", encoding="utf-8") as errors:
        # The SDK normally writes child stderr to the console. Suppress raw errors here.
        from mcp import ClientSession, stdio_client
        async with stdio_client(params, errlog=errors) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                listed = await session.list_tools()
                if not EXPECTED_TOOLS.issubset({tool.name for tool in listed.tools}):
                    raise SetupError("MCPの機能を確認できませんでした。セットアップを再実行してください。")
                result = await session.call_tool("get_kicho_guide")
                if result.is_error or not result.structured_content or not result.structured_content.get("credential_configured"):
                    raise SetupError("API設定を読み込めませんでした。セットアップを再実行してください。")


def setup(uv: Path, install_root: Path, config_path: Path, env_file: Path | None = None,
          workspace: Path | None = None, non_interactive: bool = False) -> dict:
    options = previous_options(config_path)
    install_root = install_root.expanduser().resolve()
    install_root.mkdir(parents=True, exist_ok=True)
    workspace = (workspace or options.get("--workspace") or install_root / "data").expanduser().resolve()
    candidates = [env_file] if env_file else []
    if options.get("--env-file"):
        candidates.append(options["--env-file"])
    candidates.append(ROOT / ".env")
    if env_file is not None and not env_file.is_file():
        raise SetupError("指定されたAPI設定ファイルが見つかりません。")
    print("1/4 API設定を準備しています。", flush=True)
    credentials = install_root / ".env"
    ensure_credentials(credentials, candidates, non_interactive)
    print("2/4 kicho-botの本体を保存しています。", flush=True)
    installed = install_version(ROOT / "kicho-bot", install_root)
    config = configuration.make_config(uv, credentials, workspace, installed / "scripts/mcp_server.py")
    entry = config["mcpServers"]["kicho-bot"]
    print("3/4 Python環境とMCP接続を確認しています（Jevへの送信・課金なし）。", flush=True)
    checked = subprocess.run([entry["command"], *entry["args"], "--check"], capture_output=True,
                             text=True, encoding="utf-8", errors="replace", timeout=240)
    if checked.returncode:
        raise SetupError("起動確認に失敗しました。ネットワークとフォルダーの権限を確認して再実行してください。")
    try:
        asyncio.run(asyncio.wait_for(verify_connection(config), timeout=60))
    except Exception:
        # Protocol errors may include subprocess output; never display the raw exception.
        raise SetupError("MCPに接続できませんでした。Claude Desktop設定は変更していません。再実行してください。") from None
    print("4/4 Claude Desktopに登録しています。", flush=True)
    backup = configuration.merge_config(config_path, config, replace=True)
    status = {"status": "ready", "workspace": str(workspace), "env_file": str(credentials),
              "server": str(installed / "scripts/mcp_server.py"), "config_path": str(config_path),
              "backup": str(backup) if backup else None}
    (install_root / "setup-status.json").write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")
    print("セットアップが完了しました。Claude Desktopを完全に終了して、再起動してください。", flush=True)
    print(f"仕訳案の保存先: {workspace}", flush=True)
    print("APIキーの有効性・残高と、Desktop画面上の接続は別途確認してください。", flush=True)
    return status


def main() -> int:
    parser = argparse.ArgumentParser(description="kicho-botをClaude Desktop向けに自動セットアップ")
    parser.add_argument("--uv", type=Path, required=True)
    parser.add_argument("--install-root", type=Path, required=True)
    parser.add_argument("--config", type=Path)
    parser.add_argument("--env-file", type=Path)
    parser.add_argument("--workspace", type=Path)
    parser.add_argument("--non-interactive", action="store_true")
    args = parser.parse_args()
    try:
        config_path = args.config or configuration.default_config_path()
        setup(args.uv, args.install_root, config_path, args.env_file, args.workspace, args.non_interactive)
    except SetupError as exc:
        print(f"セットアップを完了できません: {exc}", file=sys.stderr)
        return 1
    except (OSError, ValueError, subprocess.TimeoutExpired):
        print("セットアップを完了できません。ネットワーク、保存先の権限、既存設定の形式を確認してください。", file=sys.stderr)
        return 1
    except (KeyboardInterrupt, EOFError):
        print("セットアップを中断しました。再実行して続けられます。", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
