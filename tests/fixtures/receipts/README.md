# 架空の領収書データ20件

全件がテスト専用の架空データです。店舗・取引・社内方針は実在しません。

- `receipts/`: 人が読める領収書風テキスト。画像ではありません。
- `inputs/`: kicho-botに渡す抽出済みJSON。実画像からOCRしたものではありません。
- `manifest.json`: 入力パスと期待する科目・税カテゴリ・振り分け。期待値はAPIに送信しません。

通常経費、販売目的の仕入、私用購入、目的不明の飲食、税率混在、金額・日付欠損、
税額不整合、高額機器、品目不明、現金売上を含みます。
期待値は架空事業の社内方針を元にしたテスト上の想定であり、税務判断の正解データではありません。

プロジェクト直下から再実行します（実APIを20回呼びます）。出力先は未使用のフォルダー名にしてください。

```bash
uv run --env-file .env --frozen --script tests/run-receipt-evaluation.py --out tests/results/receipts-next-run
```

生成器から再作成する場合：

```bash
uv run --with 'pydantic>=2.12,<3' python tests/create-receipt-fixtures.py
```

入力JSONを手で変えた場合、生成器の再実行で上書きされます。

[実API検証の要約](../../../docs/evaluation.md)も参照してください。
