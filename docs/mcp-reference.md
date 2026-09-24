# MCPのツールと接続設定

Claude Desktopでの導入・日常の操作は[README](../README.md)を参照してください。このページはMCPツールの仕様と、他のクライアントへ接続する場合の補足です。

## 公開しているツール

| ツール | 内容 |
|---|---|
| `get_kicho_guide` | 抽出スキーマ、科目表、手順、接続先の確認。キー本体は返さない |
| `classify_receipt` | Jev分類・仕訳案の保存。`dry_run=true`なら送信も保存もしない |
| `list_drafts` | 顧客IDに一致する仕訳案の一覧 |
| `get_draft` | 証憑IDによる仕訳案の詳細取得 |
| `prepare_freee_review` | 任意のfreee確認キュー作成・更新 |
| `open_freee_review` | 人が確認するローカル画面のURLを取得 |

読取はホストが行い、抽出済みJSONをツールへ渡します。取引の確定・CSV出力はユーザーがブラウザーで行います。確認画面はMCP接続終了時に停止します。

## 接続設定の生成

リポジトリ直下で実行すると、実際の絶対パスを入れた設定JSONを表示します。

```bash
uv run --no-project python scripts/configure-mcp.py
```

必要に応じて`--uv`、`--env-file`、`--workspace`で場所を指定できます。設定にキー本体は含みません。

## Codexなどへの接続

stdio対応クライアントに、生成した設定の`command`と`args`を登録します。Codexの設定例:

```toml
[mcp_servers.kicho-bot]
command = "/absolute/path/to/uv"
args = ["run", "--env-file", "/absolute/path/to/kicho-bot/.env", "--frozen", "--script", "/absolute/path/to/kicho-bot/kicho-bot/scripts/mcp_server.py", "--workspace", "/absolute/path/to/kicho-bot/work/mcp"]
startup_timeout_sec = 60
tool_timeout_sec = 60
```

Windowsでは`command`と各引数をWindowsの絶対パスへ置き換えます。[Codex公式のMCP設定](https://developers.openai.com/codex/mcp/)を参照してください。

ローカルstdioサーバーを公開HTTPサーバーとして接続することはできません。
