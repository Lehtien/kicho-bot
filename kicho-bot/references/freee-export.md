# freee取引への変換と確認

内部の借方・貸方は監査用に保持し、freeeには「取引インポートCSV」を出す。
freeeの自動仕訳ルールの代替ではなく、証憑の読取・顧客方針を使った判定・人の確認を担当する。

## 顧客別マッピング

`assets/freee-mapping.example.json`を作業フォルダーへコピーし、顧客ごとに編集する。
同梱の名前は例であり、実際のfreeeマスタを取得・確認したものではない。

- `client_id`: 抽出JSONの`client.client_id`と一致させる。
- `expense_accounts`: ボットの借方ID → freee上の勘定科目名。
- `income_accounts`: ボットの貸方ID → freee上の勘定科目名。
- `wallets`: カード・銀行ごとの識別キー → freee口座名、内部相手科目ID、同期状態。`card_payable`だけから実際のカードを推測しない。
- `unpaid_accounts`: 未決済として扱える相手科目ID。支出の買掛金・未払金、収入の売掛金など、顧客科目に合わせる。
- `tax_rules`: 収支・税カテゴリ・適格請求書区分・有効期間が一致するルールを1件だけ適用する。名前はfreee表示と完全一致させる。免税事業者等からの仕入・経過措置・軽減税率などを通常の10%へ自動変換しない。該当ルールがなければ要確認にする。
- `partner_names`: 証憑の取引先名からfreee取引先名への任意の対応。なければ証憑の名前を使う。未登録の取引先・品目はfreee側で新規作成され得るため確認画面で確かめる。
- `verified`: マスタと照合し、ユーザーが使用を認めた対応表のみ`true`。エージェントがテンプレートをコピーしただけで`true`にしない。

CSVでは名前を使う。将来APIを追加する場合は事業所別の`account_item_id`・`tax_code`等を別途取得する。ボットのIDをfreeeのIDとして送らない。

## 抽出JSONに付けるfreee用の事実

`extracted.transaction_type`を`expense`（支出）または`income`（収入）に設定する。
領収書中心の既存データとの互換性のため省略時は`expense`だが、判別不能なら`unknown`とする。
下記`freee_context`を`extracted`の外側に追加する。

```json
{
  "source_status": "receipt_only",
  "statement_id": null,
  "settlement_status": "paid",
  "wallet_key": "cash",
  "payment_date": "2026-09-18",
  "due_date": null,
  "item": ""
}
```

- `source_status`: 既存取引・同期明細がないことを確認した場合のみ`receipt_only`。同期済みは`synced_statement`、不明は`unknown`。
- `statement_id`: 同期明細を識別できる場合のID。設定済みなら必ず提案扱い。
- `settlement_status`: `paid`、`unpaid`、`unknown`。未決済なら`wallet_key`・`payment_date`をnullにする。
- `wallet_key`: 顧客対応表の実口座キー。カードの引落口座ではなく、利用したカード口座を指定する。
- `payment_date`: 実際の決済日。証憑日付を根拠なしに転記しない。
- `item`: freeeの品目名。商品の明細は備考に残るため、品目タグを増やしたくなければ空欄にする。

同期口座の取引または同期明細は`action = suggestion`として確認画面に表示し、新規取引CSVには出さない。同期状態が不明なものも出力しない。このローカル機能はfreeeに照会しないため、同期・既存登録の確認はユーザーまたは取得済みマスタ／明細の事実に基づく。

## キューを作って確認する

Jev分類結果をJSONファイルとして保存してから実行する。

```bash
uv run --script "$KICHO_SKILL_DIR/scripts/freee_deals.py" draft.json --mapping client-freee.json --out review-queue.json
uv run --script "$KICHO_SKILL_DIR/scripts/review_freee.py" review-queue.json
```

表示されたローカルURLをユーザーが開き、各行の「この取引を確定」を押す。
「確定した取引をCSV出力」でUTF-8 BOM付きCSVをダウンロードする。
**ユーザーが対象行を確認して明示的に確定を指示するまでは、確認APIを呼んだり、確認キューの確定記録を書き込まない。**
スキルの実装・検証の依頼だけでは実データの確定を意味しない。テスト用データは隔離して検証する。

`route = candidate_auto`、マッピング完了、同期重複なし、人の確定の全条件が必要。
`review`は確定できない。証憑・顧客方針を修正して再判定する。
顧客ごとに同じキューファイルへ追加する。再判定で同じ証憑IDなら更新される。
内容や対応表が変わると確定は失効する。出力済みの証憑IDは再出力されない。
過去のCSVは出力履歴から再ダウンロードできる。

CSVの再ダウンロードは再インポートの許可を意味しない。freeeの管理番号は重複排除キーではない。
別キューを作った場合や証憑の抽出内容を変えた場合は同一証憑を検出できないことがあるため、既存取引との照合が必要。

## 出力の範囲

- 単一明細の収入・支出、税込金額、内税。複合仕訳・返金・部分決済は対象外。
- 未決済は決済日・決済口座・決済金額を空欄にする。
- CSVをfreeeの「取引データのインポート」で確認して取り込む。振替伝票インポートではない。
- OAuth接続や`POST /api/1/deals`、同期明細の直接更新は実装しない。

出典: [freee公式の取引インポート仕様](https://support.freee.co.jp/hc/ja/articles/202847320)（2026-09-24確認）。
