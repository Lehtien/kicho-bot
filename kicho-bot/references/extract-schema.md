# Extract schema

Codex or Claude fills this object before any Jev call. Leave a field null rather than guessing.

```json
{
  "source_type": "receipt | invoice | statement | handwritten | unknown",
  "vendor": "string or null",
  "date": "YYYY-MM-DD or null",
  "currency": "JPY",
  "amount_incl_tax": 0,
  "amount_excl_tax": null,
  "tax_amount": null,
  "tax_rate_hint": "0.10 | 0.08 | mixed | unknown",
  "invoice_number": null,
  "qualified_invoice": "yes | no | unknown",
  "payment_method": "cash | credit_card | bank | e_money | unknown",
  "items": [
    {"name": "string", "amount_incl_tax": 0, "qty": 1}
  ],
  "raw_text": "OCR or typed text",
  "needs_ocr_review": false,
  "extraction_notes": []
}
```

Arithmetic check after extraction

- if tax and both amounts exist, `|incl - excl - tax| <= 1`
- if only incl and rate hint exist, do not force a tax amount unless the receipt printed one

`needs_ocr_review` is true when vendor, date, or amount_incl_tax is missing.

Save this object under `extracted`; sibling objects are `client`, optional
`history_hints`, and optional `freee_context`. Amounts are integer yen or null,
never guessed zero. `extracted.transaction_type` is `expense`, `income`, or
`unknown` (omitted values default to expense for existing receipt inputs).
For freee, set `client.client_id` and follow [freee-export.md](freee-export.md).
