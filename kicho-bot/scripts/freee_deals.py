#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["pydantic>=2.12,<3"]
# ///
"""Map journal drafts to reviewable freee deals and export confirmed rows."""
from __future__ import annotations

import argparse
import csv
import glob
import hashlib
import io
import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator
from cli_io import configure_stdio

from classify_journal import build_payload, draft_id, format_entry, route
from schemas import Chart, ExtractedDocument, JsonValue, StrictModel, Text, validate_response

CSV_HEADERS = [
    "収支区分", "管理番号", "発生日", "決済期日", "取引先コード", "取引先", "勘定科目",
    "税区分", "金額", "税計算区分", "税額", "備考", "品目", "部門",
    "メモタグ（複数指定可、カンマ区切り）", "セグメント1", "セグメント2", "セグメント3",
    "決済日", "決済口座", "決済金額",
]


class Wallet(StrictModel):
    name: Text | None
    journal_account_ids: list[Text]
    sync_status: Literal["synced", "not_synced", "unknown"]


class TaxRule(StrictModel):
    direction: Literal["expense", "income"]
    category: Text
    qualified_invoice: Literal["yes", "no", "unknown"]
    name: Text
    valid_from: str
    valid_to: str

    @model_validator(mode="after")
    def dates(self) -> TaxRule:
        from schemas import Extracted
        Extracted.calendar_date(self.valid_from)
        Extracted.calendar_date(self.valid_to)
        if self.valid_from > self.valid_to:
            raise ValueError("invalid tax-rule date range")
        return self


class Mapping(StrictModel):
    client_id: Text
    verified: bool
    expense_accounts: dict[str, Text]
    income_accounts: dict[str, Text]
    wallets: dict[str, Wallet]
    unpaid_accounts: dict[str, list[Text]]
    tax_rules: list[TaxRule]
    partner_names: dict[str, Text] = Field(default_factory=dict)


class Draft(StrictModel):
    draft_id: Text
    provider: Literal["typesafe", "vercel"]
    model: Text
    extracted_document: ExtractedDocument
    chart: Chart
    route: Literal["review", "candidate_auto"]
    journal: dict[str, JsonValue]
    answers: dict[str, JsonValue]
    usage: dict[str, int]

    @model_validator(mode="after")
    def consistent(self) -> Draft:
        document = self.extracted_document.model_dump()
        chart = self.chart.model_dump()
        validate_response({"model": self.model, "answers": self.answers, "usage": self.usage},
                          build_payload(document, chart, self.model))
        if self.draft_id != draft_id(document):
            raise ValueError("draft identity mismatch")
        if self.route != route(document, self.answers):
            raise ValueError("draft routing mismatch")
        if self.journal != format_entry(document, self.answers, chart):
            raise ValueError("journal differs from source or model answers")
        return self


class Confirmation(StrictModel):
    revision: Text
    confirmed_at: Text


class ExportBatch(StrictModel):
    batch_id: Text
    created_at: Text
    draft_ids: list[Text]
    csv_text: str


class Queue(StrictModel):
    version: Literal[1] = 1
    mapping: Mapping
    drafts: list[Draft]
    confirmations: dict[str, Confirmation] = Field(default_factory=dict)
    exports: list[ExportBatch] = Field(default_factory=list)

    @model_validator(mode="after")
    def unique_drafts(self) -> Queue:
        ids = [draft.draft_id for draft in self.drafts]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate draft IDs")
        if any(d.extracted_document.client.client_id != self.mapping.client_id for d in self.drafts):
            raise ValueError("client mismatch")
        return self


def digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def unsafe_cell(value: object) -> bool:
    return isinstance(value, str) and ("\x00" in value or value.lstrip().startswith(("=", "+", "-", "@")))


def map_deal(draft: Draft, mapping: Mapping) -> dict:
    extracted = draft.extracted_document.extracted
    context = draft.extracted_document.freee_context
    journal = draft.journal
    reasons: list[str] = []
    if draft.route != "candidate_auto":
        reasons.append("Jev判定が要レビューです。証憑・方針を確認し再判定してください。")
    if not mapping.verified:
        reasons.append("顧客別マッピングが未確認です。freeeのマスタと照合してください。")
    if draft.extracted_document.client.client_id != mapping.client_id:
        reasons.append("顧客IDが対応表と一致しません。")

    direction = extracted.transaction_type
    account_side, payment_side = ("debit", "credit") if direction == "expense" else ("credit", "debit")
    account_map = mapping.expense_accounts if direction == "expense" else mapping.income_accounts
    account_name = account_map.get(journal[account_side]["id"])
    if not account_name or direction == "unknown":
        reasons.append("収支区分または勘定科目の対応が未設定です。")

    tax_rules = [rule for rule in mapping.tax_rules
                 if rule.direction == direction and rule.category == journal["tax_category"]
                 and rule.qualified_invoice == extracted.qualified_invoice
                 and extracted.date is not None and rule.valid_from <= extracted.date <= rule.valid_to]
    if len(tax_rules) != 1:
        reasons.append("発生日・収支・適格請求書区分に一致する税区分を1件に確定してください。")

    wallet = mapping.wallets.get(context.wallet_key) if context.wallet_key else None
    synced = (context.source_status == "synced_statement" or context.statement_id is not None
              or (wallet is not None and wallet.sync_status == "synced"))
    if synced:
        action = "suggestion"
        reasons.append("同期済み明細への科目提案です。新規取引CSVには出力しません。")
    else:
        action = "new_deal"
        if context.source_status != "receipt_only":
            reasons.append("既存明細・取引との重複確認が必要です。")

    payment_date, payment_account, payment_amount = "", "", ""
    if context.settlement_status == "paid":
        if wallet is None or wallet.name is None or context.payment_date is None:
            reasons.append("決済日と、実際に利用したfreee口座の指定が必要です。")
        elif journal[payment_side]["id"] not in wallet.journal_account_ids:
            reasons.append("決済口座と内部仕訳の相手科目が一致しません。")
        else:
            payment_date = context.payment_date.replace("-", "/")
            payment_account = wallet.name
            payment_amount = extracted.amount_incl_tax
        if wallet is not None and wallet.sync_status == "unknown":
            reasons.append("決済口座の同期状態が未確認です。")
    elif context.settlement_status == "unpaid":
        if journal[payment_side]["id"] not in mapping.unpaid_accounts.get(direction, []):
            reasons.append("未決済の指定と内部仕訳の相手科目が一致しません。")
        if context.payment_date is not None or context.wallet_key is not None:
            reasons.append("未決済では決済日と口座を空欄にしてください。")
    else:
        reasons.append("決済済み／未決済を確認してください。")

    if extracted.amount_incl_tax is None or extracted.amount_incl_tax <= 0:
        reasons.append("金額を確認してください。単一明細の正の金額のみ出力できます。")
    deal = {
        "収支区分": {"income": "収入", "expense": "支出"}.get(direction, ""),
        "管理番号": "KB-" + draft.draft_id,
        "発生日": (extracted.date or "").replace("-", "/"),
        "決済期日": (context.due_date or "").replace("-", "/"),
        "取引先コード": "",
        "取引先": mapping.partner_names.get(extracted.vendor, extracted.vendor or ""),
        "勘定科目": account_name or "",
        "税区分": tax_rules[0].name if len(tax_rules) == 1 else "",
        "金額": extracted.amount_incl_tax,
        "税計算区分": "内税",
        "税額": extracted.tax_amount if extracted.tax_amount is not None else "",
        "備考": journal["description_hint"],
        "品目": context.item,
        "決済日": payment_date,
        "決済口座": payment_account,
        "決済金額": payment_amount,
    }
    if any(unsafe_cell(value) for value in deal.values()):
        reasons.append("CSVで数式として解釈される文字列があります。内容を確認してください。")
    return {"draft_id": draft.draft_id, "route": draft.route, "action": action,
            "settlement_status": context.settlement_status,
            "statement_id": context.statement_id, "freee_deal": deal, "reasons": reasons,
            "journal": journal, "answers": draft.answers,
            "raw_text": extracted.raw_text,
            "revision": digest({"draft": draft.model_dump(), "mapping": mapping.model_dump(), "deal": deal})}


def queue_rows(queue: Queue) -> list[dict]:
    exported = {draft_id for batch in queue.exports for draft_id in batch.draft_ids}
    rows = []
    for draft in queue.drafts:
        row = map_deal(draft, queue.mapping)
        confirmation = queue.confirmations.get(draft.draft_id)
        row["confirmed"] = confirmation is not None and confirmation.revision == row["revision"]
        row["exported"] = draft.draft_id in exported
        row["can_confirm"] = not row["reasons"] and not row["exported"]
        rows.append(row)
    return rows


def confirm(queue: Queue, selected_id: str, revision: str) -> None:
    row = next((row for row in queue_rows(queue) if row["draft_id"] == selected_id), None)
    if row is None or not row["can_confirm"] or row["revision"] != revision:
        raise ValueError("確認対象が更新されたか、出力条件を満たしていません。再読込してください。")
    queue.confirmations[selected_id] = Confirmation(revision=revision, confirmed_at=now())


def create_export(queue: Queue) -> ExportBatch:
    rows = [row for row in queue_rows(queue) if row["can_confirm"] and row["confirmed"]]
    if not rows:
        raise ValueError("確定済みで未出力の取引がありません。")
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=CSV_HEADERS, lineterminator="\r\n")
    writer.writeheader()
    writer.writerows(row["freee_deal"] for row in rows)
    csv_text = buffer.getvalue()
    if len(csv_text.encode("utf-8-sig")) > 5_000_000:
        raise ValueError("CSVがfreeeの5MB上限を超えています。確認対象を分割してください。")
    batch = ExportBatch(batch_id=digest([row["revision"] for row in rows])[:24], created_at=now(),
                        draft_ids=[row["draft_id"] for row in rows], csv_text=csv_text)
    queue.exports.append(batch)
    return batch


def save_queue(path: Path, queue: Queue) -> None:
    """Atomic writes (0600 on POSIX, directory ACL on Windows), under queue_lock."""
    descriptor, temporary = tempfile.mkstemp(prefix=".kicho-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as output:
            output.write(queue.model_dump_json(indent=2))
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def load_queue(path: Path) -> Queue:
    return Queue.model_validate(json.loads(path.read_text(encoding="utf-8")))


def expand_drafts(patterns: list[str]) -> list[Path]:
    paths = []
    for pattern in patterns:
        matches = [Path(pattern)] if Path(pattern).is_file() else [Path(p) for p in sorted(glob.glob(pattern))]
        if not matches or any(not path.is_file() for path in matches):
            raise ValueError("No draft files match the input")
        paths.extend(path.resolve() for path in matches)
    return list(dict.fromkeys(paths))


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepare a freee review queue from Jev drafts")
    parser.add_argument("drafts", nargs="+", help="Draft JSON paths or quoted glob patterns")
    parser.add_argument("--mapping", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    from queue_store import queue_lock
    try:
        mapping = Mapping.model_validate(json.loads(args.mapping.read_text(encoding="utf-8-sig")))
        drafts = [Draft.model_validate(json.loads(path.read_text(encoding="utf-8-sig"))) for path in expand_drafts(args.drafts)]
        if any(draft.extracted_document.client.client_id != mapping.client_id for draft in drafts):
            raise ValueError("client mismatch")
        with queue_lock(args.out):
            queue = load_queue(args.out) if args.out.exists() else Queue(mapping=mapping, drafts=[])
            if queue.mapping.client_id != mapping.client_id:
                raise ValueError("client mismatch")
            queue.mapping = mapping
            by_id = {draft.draft_id: draft for draft in queue.drafts}
            by_id.update({draft.draft_id: draft for draft in drafts})
            queue.drafts = list(by_id.values())
            save_queue(args.out, queue)
        rows = queue_rows(queue)
        print(json.dumps({"queue": str(args.out), "drafts": len(rows),
                          "ready_for_confirmation": sum(row["can_confirm"] for row in rows),
                          "suggestions": sum(row["action"] == "suggestion" for row in rows)}, ensure_ascii=False))
        return 0
    except (OSError, ValueError):
        print("確認キューを作成できません。入力形式、顧客ID、判定JSONと対応表を確認してください。", file=sys.stderr)
        return 2


if __name__ == "__main__":
    configure_stdio()
    raise SystemExit(main())
