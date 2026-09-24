# 架空領収書20件の実API検証

検証日: 2026-09-24。公開用に集計と各ケースの結果をまとめています。表のリンク先は判定に使った入力JSONです。

Vercel AI Gateway → typesafe-ai/jev の実APIを使用。証憑テキストと抽出済みJSONは全件架空です。画像OCRや実領収書の精度評価ではありません。

- 正常完了: 20/20件（4件はエラー後に1回再試行）
- 仕訳候補 candidate_auto: 12件 / 人の確認 review: 8件
- 借方・貸方・税カテゴリ・振り分けの全項目が事前想定と一致: 17/20件
- 想定した要レビュー8ケースはすべてreviewになりました。
- 期待値をAPIに渡さず、架空事業の方針と証憑から判定しました。

## 想定との差

- 私用購入: 事業主貸・対象外は一致。貸方はカード未払金ではなく要確認になりました。reviewで停止しています。
- 目的不明の飲食: 税カテゴリも判断不能になりました。reviewで停止しています。
- 品目が「品代」だけの領収書: 税カテゴリも判断不能になりました。reviewで停止しています。

## テストで修正した点

- 決済状態がJevの入力に含まれていなかったため、未払いでも予定の振込方法から銀行支払と判定していました。決済状態を明示して、未払いを区別する指示に修正しました。
- 税カテゴリの質問で顧客方針・私用かどうかも参照するようにしました。
- 貸方・税カテゴリの確信度が低くても候補扱いになったため、借方と同じ閾値でreviewへ振り分けるようにしました。
- ローカル回帰テスト18件が成功しています。

## 接続・応答のエラー

- 今回の呼び出しは初回20件、エラー切り分け6件、修正後20件、失敗分再試行4件の合計50回です。下の一覧は修正後の各ケースの最終結果です。

- 修正後の20件一括実行ではHTTP 503が2件、応答形式の検証エラーが2件発生しました。
- その4件のみ再試行し、4件とも正常完了しました。無限リトライや別サービスへの切り替えは行っていません。
- 応答形式エラーの詳しい発生条件は未特定です。検証を緩めて通す変更はしていません。

## 各ケース

| 領収書 | 借方 | 貸方 | 税カテゴリ | 振り分け | 事前想定との比較 |
|---|---|---|---|---|---|
| [事務用ノートとペン](../tests/fixtures/receipts/inputs/01-stationery.json) | 消耗品費 | 現金 | taxable_10 | candidate_auto | 一致 |
| [客先訪問の電車代](../tests/fixtures/receipts/inputs/02-train.json) | 旅費交通費 | 現金 | taxable_10 | candidate_auto | 一致 |
| [同期済みカードのタクシー](../tests/fixtures/receipts/inputs/03-taxi-synced.json) | 旅費交通費 | 未払金_カード | taxable_10 | candidate_auto | 一致 |
| [業務専用の携帯回線](../tests/fixtures/receipts/inputs/04-mobile.json) | 通信費 | 普通預金 | taxable_10 | candidate_auto | 一致 |
| [事務所の電気料金](../tests/fixtures/receipts/inputs/05-electricity.json) | 水道光熱費 | 普通預金 | taxable_10 | candidate_auto | 一致 |
| [業務用の技術書](../tests/fixtures/receipts/inputs/06-book.json) | 新聞図書費 | 現金 | taxable_10 | candidate_auto | 一致 |
| [集客用の広告出稿](../tests/fixtures/receipts/inputs/07-advertising.json) | 広告宣伝費 | 未払金_カード | taxable_10 | candidate_auto | 一致 |
| [未払いの外注請求書](../tests/fixtures/receipts/inputs/08-outsourcing-unpaid.json) | 外注費 | 未払金 | taxable_10 | candidate_auto | 一致 |
| [専用事務所の家賃](../tests/fixtures/receipts/inputs/09-office-rent.json) | 地代家賃 | 普通預金 | taxable_10 | candidate_auto | 一致 |
| [振込手数料](../tests/fixtures/receipts/inputs/10-bank-fee.json) | 支払手数料 | 普通預金 | taxable_10 | candidate_auto | 一致 |
| [いつもの文具店だが販売用仕入](../tests/fixtures/receipts/inputs/11-resale.json) | 仕入高 | 未払金_カード | taxable_10 | candidate_auto | 一致 |
| [事業カードで私用の買い物](../tests/fixtures/receipts/inputs/12-personal.json) | 事業主貸 | 要確認 | out_of_scope | review | 差: credit |
| [飲食の相手・目的が不明](../tests/fixtures/receipts/inputs/13-dining-unclear.json) | 要確認 | 現金 | mixed_or_unknown | review | 差: tax |
| [8%食品と10%文具が混在](../tests/fixtures/receipts/inputs/14-mixed-tax.json) | 要確認 | 現金 | mixed_or_unknown | review | 一致 |
| [感熱紙が薄く金額不明](../tests/fixtures/receipts/inputs/15-amount-unreadable.json) | 消耗品費 | 現金 | mixed_or_unknown | review | 一致 |
| [日付が破れて読めない](../tests/fixtures/receipts/inputs/16-date-unreadable.json) | 旅費交通費 | 現金 | taxable_10 | review | 一致 |
| [印字金額の計算不一致](../tests/fixtures/receipts/inputs/17-tax-mismatch.json) | 消耗品費 | 現金 | taxable_10 | review | 一致 |
| [高額パソコンの資産判断](../tests/fixtures/receipts/inputs/18-expensive-laptop.json) | 工具器具備品 | 未払金_カード | taxable_10 | review | 一致 |
| [新規取引先の品目が『品代』](../tests/fixtures/receipts/inputs/19-vague.json) | 要確認 | 現金 | mixed_or_unknown | review | 差: tax |
| [制作代金を現金で受領](../tests/fixtures/receipts/inputs/20-cash-income.json) | 現金 | 売上高 | taxable_10 | candidate_auto | 一致 |

## 手元で試す

[テストデータと再実行手順](../tests/fixtures/receipts/README.md)を参照してください。実APIの呼び出しにはキーが必要です。応答は実行ごとに変わる可能性があります。

生の応答・確認キュー・診断ファイルはローカルの`tests/results/`へ保存し、公開リポジトリには含めていません。この検証ではfreeeへの登録・実取引の確定・CSV出力は行っていません。
