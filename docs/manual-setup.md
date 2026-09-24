# 手動でClaude Desktopに登録する

通常は[READMEの自動セットアップ](../README.md#初回設定windows)を使ってください。このページは既存のuv・作業フォルダーを指定して手動で登録する場合の手順です。

## 初回設定（Windows）

### 1. 必要なものを用意する

- Windows側のClaude Desktop
- [uv](https://docs.astral.sh/uv/getting-started/installation/)（Pythonの実行環境・依存関係を用意するツール）
- Vercel AI GatewayまたはTypeSafe/JevのAPIキー

Claude Desktopの利用環境とJevのAPI利用料金は別です。スキルの登録、WSL、管理者権限はkicho-botの登録には不要です。

uvがない場合は、PowerShellで次を実行します。導入方法の詳細は[uv公式ガイド](https://docs.astral.sh/uv/getting-started/installation/)を参照してください。

```powershell
winget install --id astral-sh.uv -e
```

PowerShellを開き直して確認します。

```powershell
uv --version
```

Pythonはuvが必要に応じて用意するため、別途pipを設定する必要はありません。

### 2. kicho-botを取得する

リポジトリの「Code → Download ZIP」、または[ZIPをダウンロード](https://github.com/Lehtien/kicho-bot/archive/refs/heads/main.zip)から取得し、保存したい場所へ展開します。

PowerShellで、展開した`README.md`があるフォルダーへ移動します。パスは自分の環境に置き換えてください。

```powershell
Set-Location "C:\Users\your-name\Documents\kicho-bot-main"
```

以降のコマンドはこのフォルダーで実行します。Gitを使う場合は、次の方法でも取得できます。

```powershell
git clone https://github.com/Lehtien/kicho-bot.git
Set-Location kicho-bot
```

### 3. APIキーを設定する

ひな型をコピーして開きます。既存の`.env`は上書きしません。

```powershell
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
notepad .env
```

Vercel AI Gatewayを使う場合:

```dotenv
KICHO_PROVIDER=vercel
AI_GATEWAY_API_KEY=ここに自分のキー
TYPESAFE_API_KEY=
```

Jev公式を使う場合:

```dotenv
KICHO_PROVIDER=typesafe
TYPESAFE_API_KEY=ここに自分のキー
AI_GATEWAY_API_KEY=
```

設定の詳細は[VercelのTypeSafe互換API](https://vercel.com/docs/ai-gateway/sdks-and-apis/typesafe)と[TypeSafe API](https://docs.typesafe.ai/api)を参照してください。キーをチャットに貼り付ける必要はありません。

`.env`はGitの対象外です。Claude Desktopの接続設定にもキー本体を書き込まず、このファイルから読み込みます。

### 4. 起動確認する

```powershell
uv run --env-file .env --frozen --script kicho-bot/scripts/mcp_server.py --workspace work/mcp --check
```

初回はPythonや依存パッケージの取得に時間がかかることがあります。次の2項目を確認します。

- `"status": "ok"`
- `"credential_configured": true`

この確認ではJevへ送信せず、API料金も発生しません。キーの有効性や残高までは確認しません。`false`の場合は`.env`の接続先とキー名を確認してください。

### 5. Claude Desktopに登録する

```powershell
uv run --no-project python scripts/configure-mcp.py --install
```

既存の他のMCPや設定は維持します。変更前の設定は同じフォルダーへ`.bak`として保存します。別のkicho-bot設定が登録済みの場合は停止するため、設定を変更する場合だけ`--replace`を付けて再実行してください。

Claude Desktopを完全に終了して再起動し、接続ツールに`kicho-bot`が表示されることを確認します。[MCP公式のClaude Desktop接続ガイド](https://modelcontextprotocol.io/docs/develop/connect-local-servers)も参照できます。

## macOSで手動登録する

macOS版Claude Desktopとuvを用意し、ZIPを展開してターミナルでリポジトリへ移動します。uvの導入方法は[公式ガイド](https://docs.astral.sh/uv/getting-started/installation/)を参照してください。

```sh
cd /path/to/kicho-bot-main
test -f .env || cp .env.example .env
chmod 600 .env
```

`.env`をテキストエディターで開き、上記の接続先とAPIキーを設定して保存します。その後、起動確認と登録を実行します。

```sh
uv run --env-file .env --frozen --script kicho-bot/scripts/mcp_server.py --workspace work/mcp --check
uv run --no-project python scripts/configure-mcp.py --install
```

登録先は`~/Library/Application Support/Claude/claude_desktop_config.json`です。Claude Desktopを完全に終了して再起動してください。macOSでの動作は未検証です。
