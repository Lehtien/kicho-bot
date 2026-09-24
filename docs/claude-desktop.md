# Claude DesktopからMCPで使う

経理担当者が普段のチャットで使うための入口です。Claude Desktopが添付画像・PDFから内容を読み、kicho-botのMCPツールがJevで科目を判定して、ローカルへ仕訳案を保存します。freeeを使う場合は、ブラウザーで人が確認・確定してCSVを取得します。

MCP経由ではスキルの登録は不要です。初回にuv・APIキー・接続設定を用意した後は、通常の利用でコマンドを入力する必要はありません。現在のMCPは同じPCで動くローカルstdio方式です。Web版から接続する公開HTTPサーバーは含みません。

## 初回設定（Windows）

1. [READMEのWindows手順](../README.md#windowsで始める)に従いuvを用意し、このリポジトリを取得します。スキル登録のコマンドは省略できます。
2. リポジトリ直下で`.env.example`を`.env`へコピーし、VercelまたはTypeSafe/Jevのキーを設定します。
3. 次のコマンドで必要なPython依存を取得し、接続先の設定を検証します。API呼び出し・課金は発生しません。

```powershell
uv run --env-file .env --frozen --script kicho-bot/scripts/mcp_server.py --workspace work/mcp --check
```

`"status": "ok"`と`"credential_configured": true`を確認します。`false`の場合は`.env`のキーと接続先を確認してください。このチェックはAPIキーの有効性や残高までは確認しません。

4. Claude Desktopの接続設定に追加します。

```powershell
uv run --no-project python scripts/configure-mcp.py --install
```

既存の他のMCPや設定は維持します。変更前の設定は同じフォルダーへ`.bak`として保存します。すでに別のkicho-bot設定がある場合は停止します。登録先を変更する場合だけ`--replace`を付けて再実行してください。

5. Claude Desktopを完全に終了して再起動し、接続ツールに`kicho-bot`が表示されることを確認します。

設定場所はWindowsの`%APPDATA%\Claude\claude_desktop_config.json`です。macOSでは`~/Library/Application Support/Claude/claude_desktop_config.json`へ同じスクリプトで登録できます。接続設定と再起動の手順は[MCP公式のClaude Desktop接続ガイド](https://modelcontextprotocol.io/docs/develop/connect-local-servers)も参照してください。

## 普段の使い方

まずは領収書の画像やPDFをチャットへ添付して依頼します。

```text
kicho-botで、この領収書から仕訳案を作ってください。
顧客ID: client-a
事業内容: Web制作の個人事業
計上方針: 添付した顧客ルールに従ってください。
読み取れない箇所は推測せず、要確認にしてください。
今回はfreeeへの変換は不要です。
```

Claudeが`get_kicho_guide`で形式を確認し、読み取った事実を`classify_receipt`へ渡します。仕訳案と判定結果は作業フォルダーへ保存されます。翌日も同じ顧客IDを指定して一覧や詳細を取得できます。

通常の`classify_receipt`は、抽出テキスト・顧客方針・科目表を設定済みのJev接続先へ送信します。APIの利用料金が発生します。ツール実行の許可表示はClaude Desktopの設定に従います。送信せず形式だけ試す場合は「dry_run=trueで確認して」と指示します。

### freeeを使う場合

[対応表の設定](../README.md#freeeの対応表を設定する)を済ませたJSONを添付し、次のように依頼します。

```text
顧客client-aの今回の仕訳案を、添付したfreee対応表で確認キューにしてください。
対応表はfreeeの実際の設定と照合済みです。
確認画面のURLを表示してください。確定とCSV出力は私が行います。
```

返された`http://127.0.0.1:.../#...`のURLを開いて、内容を確認します。取引の確定とCSV出力は画面で行います。MCPツールによる自動確定はありません。

確認画面はMCP接続中に利用できます。Claude Desktopの終了・MCP再接続後は「確認画面を開いて」と依頼し、新しいURLを使ってください。仕訳案・確定状態・出力履歴はファイルに残ります。

### 画像・PDF・ZIPの扱い

MCPサーバー自身にはOCRエンジンを搭載していません。Claude Desktopが読める添付画像・PDFから抽出したJSONを受け取ります。ホストが読めなかった内容をMCPが補完することはありません。

このMCPは、PC内の任意のファイルを読んだりZIPを展開したりするツールを公開していません。ZIPは先に展開して必要な証憑を添付してください。Codex / Claude Codeのスキル経由では、従来どおりエージェントのファイル操作を使えます。

## 保存場所と更新

初期値はリポジトリ内の`work/mcp/`です。

```text
work/mcp/
├── drafts/       # 仕訳案JSON。証憑IDで管理
└── queues/       # 顧客ごとの確認状態・CSV出力履歴
```

別の保存場所を使う場合は、初回登録時に指定します。

```powershell
uv run --no-project python scripts/configure-mcp.py --install --workspace "C:\Users\your-name\Documents\kicho-data"
```

すでに登録済みなら`--replace`も追加します。保存先を変えても既存データは自動移動しません。同じキューを引き継ぐ場合は、Claude Desktopを終了してから保存先へデータを移してください。

MCPはリポジトリのスクリプトを直接実行します。`git pull --ff-only`などで更新し、Claude Desktopを再起動すると反映されます。リポジトリや`.env`を移動した場合は設定を登録し直してください。

## 公開しているツール

| ツール | 内容 |
|---|---|
| `get_kicho_guide` | 抽出スキーマ、科目表、手順、接続先の確認。キー本体は返さない |
| `classify_receipt` | Jev分類・仕訳案の保存。`dry_run=true`なら送信も保存もしない |
| `list_drafts` | 顧客IDに一致する仕訳案の一覧 |
| `get_draft` | 証憑IDによる仕訳案の詳細取得 |
| `prepare_freee_review` | 任意のfreee確認キュー作成・更新 |
| `open_freee_review` | 人が確認するローカル画面のURLを取得 |

## 設定を自分で編集する場合

`--install`なしで実行すると、自分の環境の絶対パスを入れた設定JSONだけを表示します。キーの値は含みません。

```powershell
uv run --no-project python scripts/configure-mcp.py
```

表示された`mcpServers`の`kicho-bot`エントリーを、既存設定へ追加できます。他のエントリーを消さないでください。`uv`がPATHにない場合は`--uv "C:\path\to\uv.exe"`を指定します。

Codexなど別のstdio対応クライアントでも、同じ`command`と`args`を登録できます。Codexの設定例:

```toml
[mcp_servers.kicho-bot]
command = "/absolute/path/to/uv"
args = ["run", "--env-file", "/absolute/path/to/kicho-bot/.env", "--frozen", "--script", "/absolute/path/to/kicho-bot/kicho-bot/scripts/mcp_server.py", "--workspace", "/absolute/path/to/kicho-bot/work/mcp"]
startup_timeout_sec = 60
tool_timeout_sec = 60
```

Windowsでは`command`と各引数をWindowsの絶対パスへ置き換えます。[Codex公式のMCP設定](https://developers.openai.com/codex/mcp/)を参照してください。

## 困ったとき

| 状況 | 対処 |
|---|---|
| ツールが表示されない | Desktopを完全終了して再起動。`--check`で依存の取得と起動確認を先に済ませる |
| `uv`が見つからない | `--uv`で実行ファイルを明示して登録 |
| Windowsで接続できない | Windows側のuv・リポジトリ・`.env`で登録。WSLのパスをそのまま使わない |
| キーが設定されていない | `.env`の接続先とキー名を確認し、Desktopを再起動 |
| 仕訳案が見つからない | 顧客IDと登録時の`--workspace`を確認 |
| 確認URLが開かない | MCPを再接続し、`open_freee_review`で新しいURLを取得 |
| 設定を戻したい | Desktopを終了し、保存された`.bak`から設定を復元 |

MCPの登録を解除する場合は、Claude Desktop設定の`mcpServers`から`kicho-bot`エントリーだけを削除します。保存済みの仕訳案・確認キューは残ります。

## 検証範囲

WindowsネイティブとWSLで各31件が成功しています。MCPクライアントによるツール一覧取得・呼出し、分類結果の保存と再接続後の取得、確認画面での確定・CSV出力、エラー時の秘密情報非表示、顧客混在の拒否を自動テストします。テストのAPI応答は架空データに隔離し、製品機能では実際のJev接続先を利用します。

Claude Desktopの画面上で添付証憑を読み、実務の仕訳を完成させる一連の操作は別途確認が必要です。
