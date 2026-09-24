# 自動セットアップの詳細

通常はREADMEの3手順（[Windows](README.md#初回設定windows) / [Mac](README.md#初回設定mac)）で導入できます。このページはPCを操作するエージェントと、設定を細かく指定する人向けです。

## エージェントにセットアップを依頼されたら

1. Claude Desktopを使うPCにリポジトリを取得・展開します。ZIPにはAPIキーを含めません。
2. ユーザーが入力できるコンソールで、リポジトリ直下のWindows用`setup.cmd`、またはMac用`setup.command`を起動します。Macではターミナルから`bash /path/to/setup.command`でも実行できます。バックグラウンド実行だけでは、ユーザーがキーを入力できません。
3. 新規のAPIキーはユーザーがセットアップ画面へ直接入力します。チャット、ツールの引数、ログにキーを記入しません。既存設定があれば自動で引き継ぎます。
4. 完了表示と本体保存先の`setup-status.json`にある`status: ready`を確認します。初期の本体保存先はWindowsが`%LOCALAPPDATA%\kicho-bot`、Macが`~/Library/Application Support/kicho-bot`です。既存の結果ファイルがあるだけでは今回の成功を意味しないため、今回の終了コード・完了表示も確認します。
5. ユーザーにClaude Desktopの完全終了・再起動を案内します。保存していない会話や作業があり得るため、Desktopを強制終了しません。

セットアップはユーザーが依頼した登録を行います。他のMCPエントリーを削除せず、既存のkicho-botエントリーだけ更新します。変更前のClaude Desktop設定を同じフォルダーへ`.bak`として保存します。

## 自動で行うこと

- uvが使えれば利用し、なければOS・CPUに合う公式バイナリを専用フォルダーへ取得。配布元のSHA-256と照合
- Python 3.11とロックされた依存関係を準備
- 接続先とAPIキーを、非表示入力でローカルの`.env`へ保存
- 本体保存先の`versions`へアプリをコピー
- MCPに接続し、ツール一覧とAPI設定の読込を確認
- 確認成功後にClaude Desktopへ登録

シェルのPATHやマシン全体のPowerShell実行ポリシーは変更しません。`setup.cmd`内の実行ポリシー指定は、その子プロセスだけに適用されます。MacではHomebrewやsudoを使わず、既存のNixなどで管理されたuvもPATH上にあれば利用します。

接続確認はJevへリクエストを送らないため、API料金は発生しません。キーの有効性・残高や、Desktopの画面操作までは検証しません。Claude Desktop自体のインストール・ログインとAPIキーの発行はユーザーが行います。

## 既存設定の引き継ぎ

API設定は次の順に使用します。

1. 自動セットアップ先の既存`.env`
2. Windowsの`-EnvFile`、Macの`--env-file`で指定したファイル
3. 既存のkicho-bot接続設定にある`--env-file`
4. 取得したリポジトリ内の`.env`
5. 見つからなければ、ユーザーが画面で入力

既存の設定ファイルは元の場所にも残します。自動セットアップ後に使うキーは、自動セットアップ先の`.env`です。

データ保存先は、Windowsの`-Workspace`またはMacの`--workspace`の指定、既存MCP設定の`--workspace`、新規の本体保存先にある`data`の順です。保存データを勝手に移動・削除しません。

本体は内容別のフォルダーへ保存します。同じ版の再実行は再利用し、新しい版のインストールでも以前の版を残します。既存の本体を直接編集していた場合は、保護のため停止します。

## 場所を指定する

WindowsではPowerShellから、必要な引数だけ指定できます。

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/setup-windows.ps1 -InstallRoot "C:\Users\your-name\Apps\kicho-bot" -Workspace "C:\Users\your-name\Documents\kicho-data"
```

Macではターミナルから実行します。パスに空白がある場合は引用符で囲みます。

```sh
bash setup.command --install-root "$HOME/Library/Application Support/kicho-bot" --workspace "$HOME/Documents/kicho-data"
```

| Windows | Mac | 用途 |
|---|---|---|
| `-InstallRoot` | `--install-root` | 本体・API設定・セットアップ結果の保存先 |
| `-Workspace` | `--workspace` | 仕訳案・確認キューの保存先 |
| `-EnvFile` | `--env-file` | 引き継ぐ既存のAPI設定ファイル |
| `-ConfigPath` | `--config` | 登録先のClaude Desktop設定ファイル。省略時は標準の場所 |
| `-NonInteractive` | `--non-interactive` | 入力を待たない。既存の有効な形式のAPI設定がなければ停止 |

APIキーを渡すコマンドライン引数はありません。エージェントによる無人実行は、ユーザーがすでに用意した設定ファイルがある場合だけ`-NonInteractive` / `--non-interactive`を使います。

## 手動インストールを継続する場合

[手動セットアップ](docs/manual-setup.md)でリポジトリのスクリプトを直接登録できます。この方式では、Git更新後のDesktop再起動で反映されます。リポジトリや`.env`の場所を変えたら、`scripts/configure-mcp.py --install --replace`で登録し直してください。
