---
name: kicho-bot
description: 日本語の証憑からデータを抽出し、TypeSafe/Jevで勘定科目を判定して確認キューとfreee取引CSVを作る。記帳、仕訳、領収書分類、確認済みのfreee出力、kicho-botの依頼に使う。Codex・Claude Code、Jev公式・Vercel AI Gatewayに対応。
metadata:
  type: workflow
  version: "1.1"
  stack: codex-or-claude-extract + jev-decide
---

# Kicho Bot

CodexまたはClaude Codeが証憑を読み、Jevが科目を選び、Pythonが検証とレビュー振り分けを行う。説明は日本語で返す。

## 実行環境と接続先

Python 3.11以上とuvを使う。依存ライブラリはスクリプトに宣言済み。
このSKILL.mdがあるディレクトリの絶対パスを `KICHO_SKILL_DIR` に設定する。
現在の作業ディレクトリや固定のインストール先に依存しない。

| 接続先 | オプション | 環境変数 | 既定モデル |
|---|---|---|---|
| Jev公式 | `--provider typesafe` | `TYPESAFE_API_KEY` | `jev-latest` |
| Vercel AI Gateway | `--provider vercel` | `AI_GATEWAY_API_KEY` | `typesafe-ai/jev` |

接続先の優先順位は `--provider`、`KICHO_PROVIDER`、設定済みキーからの自動選択。
両方のキーがあれば接続先を明示する。通信失敗時に別サービスへ自動転送しない。
モデルを変更する場合は `--model` または `KICHO_MODEL` を使う。
キー本体をチャット・ログ・ソースへ出力しない。ユーザー指定の.envは
`uv run --env-file /absolute/path/.env --script ...` で読み込める。
別のTypeSafeスキルやClaude/OpenAI APIキーは不要。

## 手順

1. 領収書、請求書、OCRテキストを[抽出スキーマ](references/extract-schema.md)と[抽出指示](assets/extract-prompt.md)に従いJSONへ変換する。画像・PDFはホストの読取手段を使う。読めない値を推測しない。Jevにはテキストと構造化データだけを渡す。
2. 入力JSONは作業フォルダーに保存する。証憑・会社設定・結果を共有スキル内に保存しない。同梱サンプルは動作確認専用で、実際の証憑に代用しない。
3. 顧客の科目表があれば `--chart /absolute/path/chart.json` を指定する。なければ同梱の個人事業向け科目表を出発点として使い、その旨を伝える。顧客方針は入力の `client`、過去の処理は `history_hints` に入れる。
4. ユーザーの依頼に含まれるJev分類を実行する。接続先指定があれば従う。キーがない場合は抽出まで進め、不足を伝える。Jevの回答や確信度を捏造しない。

   ```bash
   uv run --script "$KICHO_SKILL_DIR/scripts/classify_journal.py" /absolute/path/extracted.json --provider vercel
   uv run --script "$KICHO_SKILL_DIR/scripts/classify_journal.py" /absolute/path/extracted.json --provider typesafe
   ```

   上記から選んだ接続先のコマンドを1つ実行する。送信せず検証する場合は `--dry-run` を付ける。

5. [質問定義](references/jev-questions.md)の6問を1回のリクエストにまとめる。金額・算術・摘要をJevに生成させない。通信失敗や不正な応答で分類結果を補完しない。
6. [振り分け規則](references/routing.md)とスクリプトの `route` に従う。確信度は精度保証ではない。顧客の実データで閾値を評価する。
7. 仕訳案JSON、借方／貸方／金額を含む人間向けの仕訳、摘要、要確認事項を返す。`review` なら借方候補の上位3件と判断を進めるための質問を示す。
8. freee向けの出力では[freee取引への変換と確認](references/freee-export.md)を読む。顧客別マッピングで取引案へ写し、ローカル確認画面を開く手順を案内する。CSVは人が確定した`candidate_auto`だけに限定する。同期済み明細は新規登録せず科目提案として表示する。

## 制約

- 不明な取引先・日付・金額は `null` にし、`needs_ocr_review` を立てる。税込・税抜・税額がそろった場合は差額1円以内を検証する。
- 勘定科目は指定した表のIDだけを使う。判断できない場合は `unknown_needs_review`。
- Jevの選択を説明なしに差し替えない。税率混在や複合仕訳が必要な証憑は単一仕訳で確定しない。
- このヘルパーは仕訳案の作成まで。`candidate_auto` はレビュー閾値を通過した候補であり、自動転記の許可や記帳済みを意味しない。会計ソフトへの転記は実装していない。
- APIを変更する際は[TypeSafe公式](https://docs.typesafe.ai/api)と[VercelのTypeSafe互換API仕様](https://vercel.com/docs/ai-gateway/sdks-and-apis/typesafe)を確認する。
