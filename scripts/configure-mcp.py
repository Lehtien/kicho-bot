#!/usr/bin/env python3
"""Generate or merge Claude Desktop MCP configuration without exposing API keys."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import uuid

ROOT = Path(__file__).resolve().parents[1]


def make_config(uv_path: Path, env_file: Path, workspace: Path) -> dict:
    uv_path = uv_path.expanduser().resolve(strict=True)
    env_file = env_file.expanduser().resolve(strict=True)
    server = ROOT / "kicho-bot/scripts/mcp_server.py"
    if not uv_path.is_file() or not env_file.is_file() or not server.is_file():
        raise ValueError("uv、.env、MCPサーバーの場所を確認してください。")
    return {"mcpServers": {"kicho-bot": {"command": str(uv_path), "args": [
        "run", "--env-file", str(env_file), "--frozen", "--script", str(server),
        "--workspace", str(workspace.expanduser().resolve()),
    ]}}}


def default_config_path() -> Path:
    if os.name == "nt":
        appdata = os.environ.get("APPDATA")
        if not appdata:
            raise ValueError("APPDATAを確認してください。")
        return Path(appdata) / "Claude/claude_desktop_config.json"
    if sys.platform == "darwin":
        return Path.home() / "Library/Application Support/Claude/claude_desktop_config.json"
    raise ValueError("Claude Desktopを使うWindows/macOS上で実行してください。設定の表示だけなら--installを外します。")


def merge_config(path: Path, config: dict, replace: bool) -> Path | None:
    exists = path.exists()
    current = json.loads(path.read_text(encoding="utf-8-sig")) if exists else {}
    if not isinstance(current, dict) or not isinstance(current.get("mcpServers", {}), dict):
        raise ValueError("既存のClaude Desktop設定のJSON形式を確認してください。")
    servers = current.setdefault("mcpServers", {})
    entry = config["mcpServers"]["kicho-bot"]
    if servers.get("kicho-bot") == entry:
        return None
    if "kicho-bot" in servers and not replace:
        raise ValueError("kicho-botは登録済みです。設定変更を反映する場合だけ--replaceを指定してください。")
    servers["kicho-bot"] = entry
    path.parent.mkdir(parents=True, exist_ok=True)
    backup = None
    if exists:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        backup = path.with_name(f"{path.name}.{stamp}.{uuid.uuid4().hex[:8]}.bak")
        shutil.copy2(path, backup)
    descriptor, temporary = tempfile.mkstemp(prefix=".kicho-config-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as output:
            json.dump(current, output, ensure_ascii=False, indent=2)
            output.write("\n")
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return backup


def main() -> int:
    parser = argparse.ArgumentParser(description="Claude Desktop向けMCP設定を生成・登録します。")
    parser.add_argument("--uv", type=Path, help="uv実行ファイルのパス（省略時はPATHから検索）")
    parser.add_argument("--env-file", type=Path, default=ROOT / ".env")
    parser.add_argument("--workspace", type=Path, default=ROOT / "work/mcp")
    parser.add_argument("--install", action="store_true", help="Claude Desktopの既存設定へ追加")
    parser.add_argument("--replace", action="store_true", help="既存のkicho-bot設定の置換を許可")
    parser.add_argument("--config", type=Path, help="設定ファイルの場所を明示する場合")
    args = parser.parse_args()
    try:
        uv = args.uv or shutil.which("uv")
        if not uv:
            raise ValueError("uvが見つかりません。--uvで実行ファイルのパスを指定してください。")
        config = make_config(Path(uv), args.env_file, args.workspace)
        if args.install:
            path = args.config.expanduser().resolve() if args.config else default_config_path()
            backup = merge_config(path, config, args.replace)
            print(f"登録済み: {path}")
            if backup:
                print(f"変更前のバックアップ: {backup}")
            print("Claude Desktopを完全に終了し、再起動してください。")
        else:
            print(json.dumps(config, ensure_ascii=False, indent=2))
    except json.JSONDecodeError:
        parser.exit(1, "設定JSONを読み取れません。元の設定は上書きしていません。\n")
    except OSError:
        parser.exit(1, "設定できません。ファイルの場所と読書き権限を確認してください。\n")
    except ValueError as exc:
        parser.exit(1, f"設定できません: {exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
