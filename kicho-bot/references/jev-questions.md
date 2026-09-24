# Jev questions for one journal draft

Send these in a single System One request. They are independent.

## debit_account — Choice

Pick the expense or asset account for the debit side.
For income (`extracted.transaction_type = income`), pick the receiving asset
or receivable instead. The credit side is then the revenue account.

Instructions sketch

```
Choose the best debit account for this Japanese bookkeeping draft.
Use extracted.vendor, extracted.items, extracted.payment_method, client.account_policy, and client.frequent_vendors.
Prefer a specific living account over 雑費.
If the vendor is in frequent_vendors, follow that mapping unless items clearly contradict it.
If evidence is too thin, choose unknown_needs_review.
```

Criteria come from the client chart plus `unknown_needs_review`.

## credit_account — Choice

```
Choose the credit account that funds this transaction.
Check settlement_status first. Unpaid service invoices use 未払金, and unpaid merchandise uses 買掛金.
A planned bank transfer does not mean cash has already left the bank account.
Cash purchase -> 現金. Card -> 未払金 or 未払金_カード. Bank transfer -> 普通預金.
Owner personal funds in a sole proprietorship -> 事業主借 when that account exists.
```

## tax_category — Choice

Criteria

- `taxable_10` 標準税率10%（支出は課税仕入、収入は課税売上）
- `reduced_8` 軽減税率8%（支出は課税仕入、収入は課税売上）
- `non_taxable` 非課税
- `out_of_scope` 不課税・対象外
- `mixed_or_unknown` 混在または判断不能

Use business purpose and client.account_policy as well as the printed tax rate.
If the client policy excludes a personal purchase from business expenses, do not
classify it as a business taxable purchase just because its receipt prints a rate.

## matches_client_rule — Noul

```
The proposed treatment is consistent with client.account_policy and client.frequent_vendors given extracted.vendor and extracted.items.
```

## unusual — Noul

```
This transaction is unusual for this client and should not be posted without a person looking at it.
True examples include a new vendor with a large amount, entertainment language on the receipt, mixed tax rates, or a personal-looking item at a business vendor.
```

## review_priority — Score

Levels

0. routine same-as-usual purchase
1. small uncertainty, skim is enough
2. needs a bookkeeper look
3. stop, tax or policy risk

## Do not ask Jev

- the numeric amount
- whether 80 + 8 = 88
- a free-text 摘要
- account names outside the supplied chart
