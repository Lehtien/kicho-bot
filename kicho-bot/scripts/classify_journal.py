#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["pydantic>=2.12,<3"]
# ///
"""Classify a receipt extracted by Codex or Claude, via TypeSafe or Vercel."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

from pydantic import ValidationError
from cli_io import configure_stdio, write_json
from schemas import Chart, ExtractedDocument, validate_response

PROVIDERS = {
    "typesafe": ("https://api.typesafe.ai/v1/systemone", "jev-latest", "TYPESAFE_API_KEY"),
    "vercel": ("https://ai-gateway.vercel.sh/typesafe/v1/systemone", "typesafe-ai/jev", "AI_GATEWAY_API_KEY"),
}
ROOT = Path(__file__).resolve().parents[1]
CHART_PATH = ROOT / "assets" / "chart-of-accounts.ja.json"


def load_json(path: Path) -> dict:
    with path.open(encoding="utf-8-sig") as fh:
        return json.load(fh)


def criteria_from_accounts(accounts: list[dict]) -> dict[str, str]:
    out = {}
    for acc in accounts:
        label = acc["name"]
        hint = acc.get("when_to_use") or label
        out[acc["id"]] = f"{label}。{hint}"
    return out


def build_payload(extracted_doc: dict, chart: dict, model: str = "jev-latest") -> dict:
    extracted = extracted_doc["extracted"]
    client = extracted_doc.get("client", {})
    debit_criteria = criteria_from_accounts(chart["debit_accounts"])
    credit_criteria = {
        acc["id"]: acc["name"] for acc in chart["credit_accounts"]
    }
    state = {
        "extracted": extracted,
        "client": client,
        "chart_id": chart.get("chart_id"),
        "chart": {"debit_accounts": chart["debit_accounts"], "credit_accounts": chart["credit_accounts"]},
        "history_hints": extracted_doc.get("history_hints", {}),
        "settlement_status": extracted_doc.get("freee_context", {}).get("settlement_status", "unknown"),
    }
    return {
        "model": model,
        "state": state,
        "questions": {
            "debit_account": {
                "type": "choice",
                "instructions": (
                    "Choose the best debit account for this Japanese bookkeeping draft. "
                    "For income in `extracted.transaction_type`, choose the receiving asset or receivable; "
                    "if `settlement_status` is unpaid, choose a receivable, not cash or a bank balance. "
                    "for expenses choose the expense or asset purchased. "
                    "Use `extracted.vendor`, `extracted.items`, `client.account_policy`, "
                    "and `client.frequent_vendors`. Prefer a specific living account over 雑費. "
                    "If the vendor mapping and the items conflict, trust the items. "
                    "If evidence is too thin, choose unknown_needs_review."
                ),
                "criteria": debit_criteria,
            },
            "credit_account": {
                "type": "choice",
                "instructions": (
                    "For income in `extracted.transaction_type`, choose the revenue account. "
                    "For expenses: "
                    "First check `settlement_status`, `extracted.raw_text`, and `extracted.extraction_notes`. "
                    "An unpaid invoice creates a payable: use 買掛金 for merchandise or 未払金 for services. "
                    "Do not use cash or bank for an unpaid invoice even if bank transfer is the planned method. "
                    "For paid purchases use `extracted.payment_method`: cash is 現金, card is 未払金_カード, bank is 普通預金. "
                    "Owner personal funds in a sole proprietorship is 事業主借 when that account exists."
                ),
                "criteria": credit_criteria,
            },
            "tax_category": {
                "type": "choice",
                "instructions": (
                    "Choose the consumption-tax category using `extracted.tax_rate_hint`, "
                    "`extracted.items`, `extracted.transaction_type`, and `extracted.qualified_invoice`. "
                    "Also check business purpose in `extracted.extraction_notes` and `client.account_policy`. "
                    "When the client policy treats a purchase as personal/non-business and out of scope, "
                    "choose out_of_scope rather than a business purchase tax category based only on the printed rate."
                ),
                "criteria": {
                    "taxable_10": "標準税率10パーセント（支出は課税仕入、収入は課税売上）",
                    "reduced_8": "軽減税率8パーセント（支出は課税仕入、収入は課税売上）",
                    "non_taxable": "非課税取引",
                    "out_of_scope": "不課税または対象外",
                    "mixed_or_unknown": "混在または判断不能",
                },
            },
            "matches_client_rule": {
                "type": "noul",
                "instructions": (
                    "The natural account treatment is consistent with `client.account_policy` "
                    "and `client.frequent_vendors` given `extracted.vendor` and `extracted.items`."
                ),
            },
            "unusual": {
                "type": "noul",
                "instructions": (
                    "This transaction is unusual for this client and should not be posted "
                    "without a person looking at it."
                ),
            },
            "review_priority": {
                "type": "score",
                "instructions": "How much human attention should this draft get before posting?",
                "criteria": [
                    "Routine same-as-usual purchase",
                    "Small uncertainty, a skim is enough",
                    "Needs a bookkeeper look",
                    "Stop, tax or policy risk",
                ],
            },
        },
    }


def route(extracted_doc: dict, answers: dict) -> str:
    extracted = extracted_doc["extracted"]
    debit = answers.get("debit_account", {})
    credit = answers.get("credit_account", {})
    tax = answers.get("tax_category", {})
    unusual = answers.get("unusual", {}).get("noul", 0)
    matches = answers.get("matches_client_rule", {}).get("noul", 1)
    priority = answers.get("review_priority", {}).get("score", 0)
    if extracted.get("needs_ocr_review"):
        return "review"
    if any(extracted.get(field) is None for field in ("vendor", "date", "amount_incl_tax")):
        return "review"
    amounts = [extracted.get(field) for field in ("amount_incl_tax", "amount_excl_tax", "tax_amount")]
    if all(amount is not None for amount in amounts) and abs(amounts[0] - amounts[1] - amounts[2]) > 1:
        return "review"
    if extracted.get("tax_rate_hint") == "mixed":
        return "review"
    if extracted.get("transaction_type") == "unknown":
        return "review"
    if debit.get("choice") == "unknown_needs_review":
        return "review"
    if credit.get("choice") == "unknown_needs_review":
        return "review"
    if (debit.get("confidence") or 0) < 0.62:
        return "review"
    if (credit.get("confidence") or 0) < 0.62:
        return "review"
    if (tax.get("confidence") or 0) < 0.62:
        return "review"
    if unusual > 0.55:
        return "review"
    if (priority or 0) >= 2.0:
        return "review"
    if tax.get("choice") == "mixed_or_unknown":
        return "review"
    if matches < 0.45:
        return "review"
    return "candidate_auto"


def draft_id(extracted_doc: dict) -> str:
    """Stable receipt identity across reclassification and freee mapping changes."""
    identity = {"client_id": extracted_doc.get("client", {}).get("client_id"),
                "extracted": extracted_doc["extracted"]}
    return hashlib.sha256(json.dumps(identity, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:24]


def call_jev(payload: dict, endpoint: str, api_key: str) -> dict:
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        endpoint,
        data=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def format_entry(extracted_doc: dict, answers: dict, chart: dict) -> dict:
    debit_names = {acc["id"]: acc["name"] for acc in chart["debit_accounts"]}
    credit_names = {acc["id"]: acc["name"] for acc in chart["credit_accounts"]}
    extracted = extracted_doc["extracted"]
    debit_id = answers.get("debit_account", {}).get("choice")
    credit_id = answers.get("credit_account", {}).get("choice")
    amount = extracted.get("amount_incl_tax")
    return {
        "date": extracted.get("date"),
        "debit": {"id": debit_id, "name": debit_names.get(debit_id), "amount": amount},
        "credit": {"id": credit_id, "name": credit_names.get(credit_id), "amount": amount},
        "tax_category": answers.get("tax_category", {}).get("choice"),
        "vendor": extracted.get("vendor"),
        "description_hint": f"{extracted.get('vendor') or '取引先不明'} {', '.join(i.get('name', '') for i in extracted.get('items') or [])}",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Classify an extracted receipt with Jev")
    parser.add_argument("extracted_json")
    parser.add_argument("--chart", default=str(CHART_PATH))
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--out", type=Path, help="Write UTF-8 JSON directly, without shell redirection")
    parser.add_argument("--provider", choices=tuple(PROVIDERS), default=os.environ.get("KICHO_PROVIDER"))
    parser.add_argument("--model", help="Override the selected provider's model")
    args = parser.parse_args()

    provider = args.provider
    if provider is None:
        available = [name for name, (_, _, key) in PROVIDERS.items() if os.environ.get(key)]
        if len(available) > 1:
            parser.error("両方のAPIキーが設定されています。--provider vercel または typesafe を指定してください。")
        provider = available[0] if available else "typesafe"
    if provider not in PROVIDERS:
        parser.error("KICHO_PROVIDERには vercel または typesafe を指定してください。")
    endpoint, default_model, key_name = PROVIDERS[provider]
    model = args.model or os.environ.get("KICHO_MODEL") or default_model

    try:
        extracted_doc = ExtractedDocument.model_validate(load_json(Path(args.extracted_json))).model_dump()
        chart = Chart.model_validate(load_json(Path(args.chart))).model_dump()
    except ValidationError as exc:
        fields = sorted({".".join(str(part) for part in error["loc"]) for error in exc.errors()})
        print("入力形式を確認してください: " + ", ".join(fields), file=sys.stderr)
        return 2
    except (OSError, ValueError):
        print("入力JSONまたは科目表を読み取れません。ファイルとJSON形式を確認してください。", file=sys.stderr)
        return 2
    payload = build_payload(extracted_doc, chart, model)

    if args.dry_run:
        return write_json({"mode": "dry-run", "provider": provider, "endpoint": endpoint, "payload": payload}, args.out)

    api_key = os.environ.get(key_name)
    if not api_key:
        print(f"{key_name}を環境変数に設定してください。送信せずに確認する場合は --dry-run を指定します。", file=sys.stderr)
        return 2
    try:
        result = validate_response(call_jev(payload, endpoint, api_key), payload)
    except urllib.error.HTTPError as exc:
        print(f"Jevへの接続に失敗しました（HTTP {exc.code}）。認証設定とサービスの状態を確認してください。", file=sys.stderr)
        return 1
    except (urllib.error.URLError, TimeoutError, OSError):
        print("Jevと通信できません。ネットワーク接続を確認してください。", file=sys.stderr)
        return 1
    except (ValueError, UnicodeError):
        print("Jevの応答形式を検証できませんでした。仕訳案は作成していません。", file=sys.stderr)
        return 1

    answers = result["answers"]
    output = {
        "draft_id": draft_id(extracted_doc),
        "extracted_document": extracted_doc,
        "chart": chart,
        "provider": provider,
        "model": result["model"],
        "route": route(extracted_doc, answers),
        "journal": format_entry(extracted_doc, answers, chart),
        "answers": answers,
        "usage": result["usage"],
    }
    return write_json(output, args.out)


if __name__ == "__main__":
    configure_stdio()
    raise SystemExit(main())
