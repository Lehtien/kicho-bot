# kicho-bot

**Claude Desktopに領収書を添付して、顧客のルールに沿った仕訳案を作るMCPサーバーです。**

Claudeが画像・PDFから内容を読み取り、TypeSafe/Jevが科目を判定します。仕訳案・判定結果はPCに保存され、チャットから確認できます。freeeを使う場合は、確認画面で人が確定した取引をCSVに出力できます。

初回の接続設定を済ませれば、普段はClaude Desktopから依頼できます。

```mermaid
flowchart LR
    A[Claude Desktopに証憑を添付] --> B[内容を読み取る]
    B --> C[kicho-bot / Jevで科目判定]
    C --> D[仕訳案をチャットで確認・PCに保存]
    D --> E[任意: freee用の確認画面]
    E --> F[人が確定してCSVを取得]
```

## 目次

- [できること](#できること)
- [初回設定（Windows）](#初回設定windows)
- [普段の使い方](#普段の使い方)
- [freeeを使う場合](#freeeを使う場合)
- [保存場所と更新](#保存場所と更新)
- [困ったとき](#困ったとき)
- [その他の環境・詳しい設定](#その他の環境詳しい設定)
- [検証と開発](#検証と開発)

## できること

- 領収書・請求書から、顧客の科目表・計上方針に沿った仕訳案を作成
- 不明な内容や判断の難しい取引を要確認として表示
- 借方・貸方・金額・税カテゴリ・判定結果をJSONで保存し、顧客ごとに再取得
- 任意でfreeeの確認キューと取引インポートCSVを作成

分類と仕訳案JSONはfreeeなしで使えます。会計ソフト専用のCSV出力は現在freeeに対応し、弥生・マネーフォワードなどへの変換は未実装です。

MCPサーバーは同じPCで動きます。WindowsネイティブとWSLで自動テストを実施しています。macOSにも登録できますが、動作は未検証です。

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

このページの「Code → Download ZIP」、または[ZIPをダウンロード](https://github.com/Lehtien/kicho-bot/archive/refs/heads/main.zip)から取得し、保存したい場所へ展開します。

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

## 普段の使い方

### 領収書から仕訳案を作る

Claude Desktopのチャットへ領収書の画像やPDFを添付して、次のように依頼します。

```text
kicho-botで、添付した領収書から仕訳案を作ってください。
顧客ID: client-a
事業内容: Web制作の個人事業
計上方針: 添付した顧客ルールに従ってください。
読み取れない箇所は推測せず、要確認にしてください。
今回は仕訳案の確認までお願いします。
```

顧客ID・事業内容・方針は実際のものに置き換えます。方針の資料がなければ、用途やよく使う科目などをチャットで伝えてください。顧客専用の科目表がなければ、同梱の個人事業向け科目表を出発点として使います。

Claudeが証憑の内容を読み、MCP経由でJevに分類を依頼します。仕訳案と判定結果は作業フォルダーへ保存されます。表示された日付・金額・科目・要確認事項を確認してください。

### 保存した仕訳案を確認する

同じ顧客IDを使って依頼します。

```text
kicho-botで、顧客client-aの保存済み仕訳案を一覧にしてください。
要確認のものについて、確認すべき点も教えてください。
```

顧客IDは継続して同じものを使います。同じ証憑IDを再分類すると保存済みの案を更新します。仕訳案が作られたことは、会計ソフトへの登録完了を意味しません。

### 画像・PDF・ZIPの扱い

読取はClaude Desktopが担当します。MCPサーバー自身にはOCRエンジンを搭載しておらず、ホストが読めなかった内容を補完しません。文字が潰れている場合は、鮮明な画像で読み直してください。

**ZIPは先に展開し、必要な画像・PDFを添付してください。** このMCPは、任意のローカルファイルを読む機能やZIP展開ツールを公開していません。

### データの送信と料金

添付資料はClaude Desktopで読み取ります。通常の分類では、抽出テキスト・顧客方針・科目表を設定済みのJev接続先へ送信し、APIの利用料金が発生します。ツール実行の許可表示はClaude Desktopの設定に従います。

送信せず入力形式だけ試したい場合は「`dry_run=true`で確認して」と指示します。この場合は仕訳案の保存も行いません。

## freeeを使う場合

### 1. 対応表を用意する

[freee対応表のひな型](kicho-bot/assets/freee-mapping.example.json)をコピーし、顧客ごとの設定を作ります。初期保存先を使っている場合のPowerShell例:

```powershell
if (-not (Test-Path work/mcp/freee-mapping.json)) { Copy-Item kicho-bot/assets/freee-mapping.example.json work/mcp/freee-mapping.json }
notepad work/mcp/freee-mapping.json
```

既存の対応表がある場合は、そのファイルを編集してください。対象事業所のfreee設定と照合する項目は次のとおりです。

| 設定 | 内容 |
|---|---|
| `client_id` | 仕訳案と同じ顧客ID |
| `expense_accounts` / `income_accounts` | 内部科目IDとfreeeの勘定科目名の対応 |
| `wallets` | 実際のカード・銀行・現金口座名と同期状態 |
| `tax_rules` | 収支・税カテゴリ・適格請求書区分・対象期間に応じたfreee税区分 |
| `verified` | ユーザーが設定と照合した場合だけ`true` |

コピーしただけでは`verified`を変更しません。口座や税区分を推測せず、該当する対応がなければ要確認とします。詳細は[freee変換仕様](kicho-bot/references/freee-export.md)を参照してください。

### 2. 確認画面を開く

照合済みの対応表JSONをClaude Desktopへ添付して依頼します。

```text
顧客client-aの今回の仕訳案を、添付したfreee対応表で確認キューにしてください。
対応表はfreeeの実際の設定と照合済みです。
確認画面のURLを表示してください。確定とCSV出力は私が行います。
```

返された`http://127.0.0.1:.../#...`を、末尾まで含めてブラウザーで開きます。

1. 証憑、日付、金額、科目、税区分、決済口座、既存登録の有無を確認します。
2. 出力可能な行の「この取引を確定」を押します。
3. 「確定した取引をCSV出力」でCSVを取得します。
4. freeeの「取引データのインポート」でプレビューを確認して取り込みます。

操作は[freee公式の取引インポート手順](https://support.freee.co.jp/hc/ja/articles/202847320)を参照してください。MCPツールによる自動確定やfreeeへの直接登録は行いません。

### 出力できる範囲

単一明細の収入・支出、全額決済または未決済、税込・内税の取引CSVに対応します。複合仕訳・税率混在・部分決済・返金は対象外です。

要確認、対応表不足、同期・決済状態が不明な行は出力しません。同期済み口座・明細は既存明細への科目提案として扱います。同期状況や取り込み済みかどうかはfreeeから自動取得しません。

同じキューの出力済み行は再出力せず、履歴から元のCSVを再取得できます。ただし、別キューや抽出内容の変更では同一証憑を検出できないことがあります。同じCSVを重複インポートしないでください。

確認画面はMCP接続中に使えます。Claude Desktopの終了や再接続後は「確認画面を開いて」と依頼し、新しいURLを取得してください。

## 保存場所と更新

### データの保存場所

初期値はリポジトリ内の`work/mcp/`です。

```text
work/mcp/
├── drafts/       # 仕訳案JSON
└── queues/       # 顧客ごとの確定状態・CSV出力履歴
```

このフォルダーを顧客情報として保管・バックアップしてください。`work/`はGitの対象外です。

別の保存先を使う場合は登録時に指定します。

```powershell
uv run --no-project python scripts/configure-mcp.py --install --workspace "C:\Users\your-name\Documents\kicho-data"
```

登録済みの設定を変更する場合は`--replace`も追加します。既存データは自動移動しません。引き継ぐ場合は、Claude Desktopを終了してから新しい保存先へデータを移してください。

### 更新する

Gitで取得した場合は、リポジトリ直下で更新してClaude Desktopを再起動します。

```powershell
git pull --ff-only
```

ZIPで取得した場合は、新しいZIPを別フォルダーへ展開し、`.env`と保存データを引き継いでから、登録スクリプトを`--install --replace`付きで再実行します。以前のフォルダーは動作確認後に整理してください。

リポジトリや`.env`を移動した場合も登録し直してください。キーを変更した場合はClaude Desktopを再起動します。

### 登録を解除する

Claude Desktopの設定ファイルにある`mcpServers`から`kicho-bot`エントリーだけを削除し、再起動します。仕訳案・確認キューは残ります。設定を戻す場合は、Desktopを終了してから保存された`.bak`を復元してください。

## 困ったとき

| 状況 | 対処 |
|---|---|
| ツールが表示されない | Desktopを完全終了して再起動。先に`--check`で依存の取得と起動確認を済ませる |
| `uv`が見つからない | 登録コマンドに`--uv "C:\path\to\uv.exe"`を付ける |
| Windowsで接続できない | Windows側のuv・リポジトリ・`.env`を使う。WSLのパスをそのまま登録しない |
| キーが未設定と言われる | `.env`の接続先とキー名を確認し、Desktopを再起動 |
| 401 / 403 | キーの有効性と接続先の利用権限を確認 |
| 429 / 503 | 利用上限やサービス状況を確認し、失敗した件だけ時間を置いて再実行 |
| 仕訳案が見つからない | 顧客IDと登録時の保存先を確認 |
| 確認URLが開かない | MCPを再接続し、新しい確認画面のURLを依頼 |
| 確定ボタンが押せない | 要確認理由、対応表、同期・決済状態を確認し、必要なら再判定 |

## その他の環境・詳しい設定

macOSではuvを用意し、リポジトリ直下で同じ起動確認・登録コマンドを実行できます。Nix / Home Managerを使っている場合は既存の宣言でuvを管理してください。

設定ファイルの場所:

- Windows: `%APPDATA%\Claude\claude_desktop_config.json`
- macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`

`--install`なしで実行すると、自分の環境の絶対パスを入れた設定JSONだけを表示します。キーの値は含みません。

```powershell
uv run --no-project python scripts/configure-mcp.py
```

現在のMCPはローカルstdio方式です。Web版から接続する公開HTTPサーバーは含みません。別のstdio対応クライアントでは、表示された`command`と`args`を登録できます。

- [MCPツール一覧・他クライアントの設定](docs/mcp-reference.md)
- [Codex / Claude Codeスキル・手動コマンド](docs/skills-and-cli.md)
- [入力JSONの仕様](kicho-bot/references/extract-schema.md)
- [freee変換と確認の仕様](kicho-bot/references/freee-export.md)

## 検証と開発

WindowsネイティブとWSLで、MCP通信を含む31件の自動テストが成功しています。分類・保存・再取得、確認画面での確定とCSV出力、顧客混在の拒否、APIキーの非表示、登録時の既存設定保護などを確認しています。

**Claude Desktopの画面上で実際の添付証憑を読み、実務の仕訳を完成させる一連の操作は未検証です。**

- [架空領収書20件のテストデータ](tests/fixtures/receipts/README.md)
- [Jev実APIでの検証結果](docs/evaluation.md)

APIを呼ばない自動テストは、リポジトリ直下で実行できます。

```powershell
uv run --with "pydantic>=2.12,<3" --with "mcp>=2.2,<3" python -m unittest discover -s tests -v
```

MCPとスキルは同じPythonの分類・確認処理を使います。MCPの入口は`kicho-bot/scripts/mcp_server.py`、Claude Desktopの登録は`scripts/configure-mcp.py`です。
