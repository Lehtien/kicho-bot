# Routing rules

Code decides the queue. Jev only supplies signals.

## Signals

- `debit_account.choice` and `debit_account.confidence`
- `credit_account.choice`
- `tax_category.choice`
- `unusual.noul`
- `review_priority.score`
- `matches_client_rule.noul`
- Codex or Claude `needs_ocr_review`

## Default policy

Route `review` if any of these hold

- OCR review needed
- vendor, date, or amount missing; tax arithmetic differs by more than 1 yen
- mixed tax rates or unknown transaction direction
- debit or credit is `unknown_needs_review`
- debit, credit, or tax-category confidence below 0.62
- unusual noul above 0.55
- review_priority score at or above 2.0
- tax_category is `mixed_or_unknown`
- matches_client_rule noul below 0.45

Otherwise return `candidate_auto`. This means a draft passed review thresholds,
not that it was posted or approved. The helper never posts entries.
Missing, malformed, or out-of-chart API answers fail validation instead of
producing a journal. freee CSV export additionally requires a verified client
mapping, confirmed absence of synced/existing entries, and explicit row confirmation.

Treat these as starting points, not published accuracy. Recalibrate on the firm's own labeled 仕訳.

## Human packet

When routing to review, Codex or Claude writes

1. proposed 仕訳
2. top 3 debit probabilities
3. the single cheapest question a person should answer
4. what would change the account
