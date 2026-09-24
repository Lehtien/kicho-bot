"""Offline contract and safety-gate tests. Fixtures never enter production queues."""
from __future__ import annotations

import copy
import csv
import io
import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "kicho-bot"
sys.path.insert(0, str(SKILL / "scripts"))

import classify_journal as classifier
from freee_deals import CSV_HEADERS, Draft, Mapping, Queue, confirm, create_export, load_queue, queue_rows, save_queue
from review_freee import make_server
from schemas import Chart, ExtractedDocument, validate_response


def document() -> dict:
    source = json.loads((SKILL / "assets/sample-extracted.json").read_text(encoding="utf-8"))
    source["client"]["client_id"] = "test-client"
    source["extracted"]["payment_method"] = "cash"
    source["freee_context"] = {"source_status": "receipt_only", "settlement_status": "paid",
                              "wallet_key": "cash", "payment_date": "2026-09-18"}
    return ExtractedDocument.model_validate(source).model_dump()


def chart() -> dict:
    return Chart.model_validate(json.loads(classifier.CHART_PATH.read_text(encoding="utf-8"))).model_dump()


def response(payload: dict, debit: str = "supplies", credit: str = "cash") -> dict:
    choices = {"debit_account": debit, "credit_account": credit, "tax_category": "taxable_10"}
    answers = {}
    for key, question in payload["questions"].items():
        if question["type"] == "choice":
            choice = choices[key]
            probabilities = {option: (0.9 if option == choice else 0.1 / (len(question["criteria"]) - 1))
                             for option in question["criteria"]}
            answers[key] = {"type": "choice", "choice": choice, "confidence": 0.9, "probabilities": probabilities}
        elif question["type"] == "noul":
            answers[key] = {"type": "noul", "noul": 0.1 if key == "unusual" else 0.9}
        else:
            answers[key] = {"type": "score", "score": 0.2, "confidence": 0.9,
                            "probabilities": {"0": 0.8, "1": 0.2, "2": 0.0, "3": 0.0},
                            "legend": {str(index): level for index, level in enumerate(question["criteria"])}}
    return {"model": payload["model"], "answers": answers, "usage": {"input_tokens": 100, "output_tokens": 10}}


def draft(source: dict | None = None, debit: str = "supplies", credit: str = "cash", low_confidence: bool = False) -> Draft:
    source = source or document()
    accounts = chart()
    result = response(classifier.build_payload(source, accounts), debit, credit)
    if low_confidence:
        result["answers"]["debit_account"]["confidence"] = 0.4
    return Draft.model_validate({"draft_id": classifier.draft_id(source), "extracted_document": source,
                                 "chart": accounts, "provider": "typesafe", "model": result["model"],
                                 "route": classifier.route(source, result["answers"]),
                                 "journal": classifier.format_entry(source, result["answers"], accounts),
                                 "answers": result["answers"], "usage": result["usage"]})


def mapping() -> Mapping:
    value = json.loads((SKILL / "assets/freee-mapping.example.json").read_text(encoding="utf-8"))
    value.update(client_id="test-client", verified=True)
    return Mapping.model_validate(value)


def queue(value: Draft | None = None) -> Queue:
    return Queue(mapping=mapping(), drafts=[value or draft()])


class ClassificationTests(unittest.TestCase):
    def test_each_provider_uses_its_endpoint_model_and_key(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "receipt.json"
            path.write_text(json.dumps(document()))
            for provider, (endpoint, model, key) in classifier.PROVIDERS.items():
                output = io.StringIO()
                def call(payload, actual_endpoint, api_key):
                    self.assertEqual((actual_endpoint, payload["model"], api_key), (endpoint, model, "test-key"))
                    return response(payload)
                with self.subTest(provider=provider), patch.dict(os.environ, {key: "test-key"}, clear=True), \
                        patch.object(sys, "argv", ["classify", str(path), "--provider", provider]), \
                        patch.object(classifier, "call_jev", side_effect=call), redirect_stdout(output):
                    self.assertEqual(classifier.main(), 0)
                result = json.loads(output.getvalue())
                self.assertEqual(result["provider"], provider)
                self.assertNotIn("test-key", output.getvalue())
                Draft.model_validate(result)

    def test_missing_or_invalid_answers_fail(self):
        payload = classifier.build_payload(document(), chart())
        for mutation in (lambda value: value["answers"].pop("credit_account"),
                         lambda value: value["answers"]["debit_account"].update(choice="invented"),
                         lambda value: value["answers"]["unusual"].update(noul=float("nan")),
                         lambda value: value["answers"]["debit_account"].update(confidence=None)):
            result = response(payload)
            mutation(result)
            with self.assertRaises(ValueError):
                validate_response(result, payload)

    def test_missing_fields_arithmetic_mixed_and_direction_require_review(self):
        answers = response(classifier.build_payload(document(), chart()))["answers"]
        for changes in ({"vendor": None}, {"date": None}, {"amount_incl_tax": None},
                        {"tax_amount": 500}, {"tax_rate_hint": "mixed"}, {"transaction_type": "unknown"}):
            source = document()
            source["extracted"].update(changes)
            self.assertEqual(classifier.route(source, answers), "review")

    def test_input_schema_rejects_wrong_types_and_bad_dates(self):
        for changes in ({"amount_incl_tax": "2178"}, {"amount_incl_tax": True},
                        {"date": "2026-02-30"}, {"vendor": " "}, {"currency": "USD"}):
            source = document()
            source["extracted"].update(changes)
            with self.assertRaises(ValueError):
                ExtractedDocument.model_validate(source)

    def test_low_credit_or_tax_confidence_requires_review(self):
        for key in ("credit_account", "tax_category"):
            answers = response(classifier.build_payload(document(), chart()))["answers"]
            answers[key]["confidence"] = 0.43
            self.assertEqual(classifier.route(document(), answers), "review")

    def test_cli_dry_run_works_outside_skill_directory(self):
        for provider in classifier.PROVIDERS:
            result = subprocess.run([sys.executable, str(SKILL / "scripts/classify_journal.py"),
                                     str(SKILL / "assets/sample-extracted.json"), "--provider", provider, "--dry-run"],
                                    cwd=tempfile.gettempdir(), capture_output=True, text=True, encoding="utf-8", check=True)
            value = json.loads(result.stdout)
            self.assertEqual(value["provider"], provider)
            self.assertEqual(value["endpoint"], classifier.PROVIDERS[provider][0])

    def test_missing_key_fails_without_fake_results(self):
        with patch.dict(os.environ, {}, clear=True), patch.object(sys, "argv", ["classify", str(SKILL / "assets/sample-extracted.json")]), \
                redirect_stdout(io.StringIO()) as output, redirect_stderr(io.StringIO()), \
                patch.object(classifier, "call_jev") as call:
            self.assertEqual(classifier.main(), 2)
            self.assertEqual(output.getvalue(), "")
            call.assert_not_called()

    def test_dual_keys_require_provider(self):
        with patch.dict(os.environ, {"TYPESAFE_API_KEY": "a", "AI_GATEWAY_API_KEY": "b"}, clear=True), \
                patch.object(sys, "argv", ["classify", "unused.json"]), redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            classifier.main()

    def test_http_error_does_not_disclose_body(self):
        error = urllib.error.HTTPError("https://example.test", 401, "secret-response", {}, io.BytesIO(b"secret-key"))
        with patch.dict(os.environ, {"TYPESAFE_API_KEY": "secret-key"}, clear=True), \
                patch.object(sys, "argv", ["classify", str(SKILL / "assets/sample-extracted.json")]), \
                patch.object(classifier, "call_jev", side_effect=error), redirect_stderr(io.StringIO()) as output:
            self.assertEqual(classifier.main(), 1)
            self.assertNotIn("secret", output.getvalue())


class FreeeTests(unittest.TestCase):
    def test_export_requires_confirmation_and_is_not_repeated(self):
        value = queue()
        with self.assertRaises(ValueError):
            create_export(value)
        row = queue_rows(value)[0]
        confirm(value, row["draft_id"], row["revision"])
        batch = create_export(value)
        reader = csv.DictReader(io.StringIO(batch.csv_text))
        self.assertEqual(reader.fieldnames, CSV_HEADERS)
        row = next(reader)
        self.assertEqual((row["勘定科目"], row["決済口座"], row["金額"], row["税計算区分"]),
                         ("消耗品費", "現金", "2178", "内税"))
        self.assertEqual(row["発生日"], "2026/09/18")
        self.assertNotIn("借方", row)
        with self.assertRaises(ValueError):
            create_export(value)

    def test_review_synced_unknown_and_unverified_are_blocked(self):
        cases = [queue(draft(low_confidence=True))]
        for status in ("synced_statement", "unknown"):
            source = document()
            source["freee_context"]["source_status"] = status
            cases.append(queue(draft(source)))
        value = queue()
        value.mapping.verified = False
        cases.append(value)
        value = queue()
        value.mapping.wallets["cash"].sync_status = "synced"
        cases.append(value)
        for value in cases:
            row = queue_rows(value)[0]
            self.assertFalse(row["can_confirm"])
            with self.assertRaises(ValueError):
                confirm(value, row["draft_id"], row["revision"])

    def test_mapping_or_draft_change_invalidates_confirmation(self):
        value = queue()
        row = queue_rows(value)[0]
        confirm(value, row["draft_id"], row["revision"])
        value.mapping.expense_accounts["supplies"] = "事務用品費"
        self.assertFalse(queue_rows(value)[0]["confirmed"])
        with self.assertRaises(ValueError):
            create_export(value)
        with self.assertRaises(ValueError):
            confirm(value, row["draft_id"], row["revision"])

    def test_unpaid_has_no_settlement_fields(self):
        source = document()
        source["freee_context"] = {"source_status": "receipt_only", "settlement_status": "unpaid"}
        value = queue(draft(source, credit="accrued"))
        row = queue_rows(value)[0]
        self.assertTrue(row["can_confirm"])
        for field in ("決済日", "決済口座", "決済金額"):
            self.assertEqual(row["freee_deal"][field], "")

    def test_income_uses_credit_account(self):
        source = document()
        source["extracted"]["transaction_type"] = "income"
        row = queue_rows(queue(draft(source, debit="cash", credit="sales")))[0]
        self.assertTrue(row["can_confirm"])
        self.assertEqual((row["freee_deal"]["収支区分"], row["freee_deal"]["勘定科目"]), ("収入", "売上高"))

    def test_mapping_failures_and_formula_cells_are_blocked(self):
        for change in (lambda value: value.mapping.expense_accounts.clear(),
                       lambda value: value.mapping.tax_rules.clear(),
                       lambda value: value.mapping.tax_rules.append(value.mapping.tax_rules[0]),
                       lambda value: setattr(value.mapping.wallets["cash"], "sync_status", "unknown"),
                       lambda value: value.mapping.partner_names.update({"Amazon.co.jp": "=1+1"})):
            value = queue()
            change(value)
            self.assertFalse(queue_rows(value)[0]["can_confirm"])

    def test_client_duplicates_and_tampered_routes_fail(self):
        value = draft()
        with self.assertRaises(ValueError):
            Queue(mapping=mapping(), drafts=[value, value])
        wrong_mapping = mapping()
        wrong_mapping.client_id = "other-client"
        with self.assertRaises(ValueError):
            Queue(mapping=wrong_mapping, drafts=[value])
        tampered = draft(low_confidence=True).model_dump()
        tampered["route"] = "candidate_auto"
        with self.assertRaises(ValueError):
            Draft.model_validate(tampered)

    def test_queue_preserves_audit_and_export_history(self):
        value = queue()
        row = queue_rows(value)[0]
        confirm(value, row["draft_id"], row["revision"])
        create_export(value)
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "queue.json"
            save_queue(path, value)
            reloaded = load_queue(path)
            self.assertEqual(reloaded, value)
            if os.name != "nt":
                self.assertEqual(path.stat().st_mode & 0o777, 0o600)


class ReviewServerTests(unittest.TestCase):
    def test_confirmation_export_auth_and_bom(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "queue.json"
            save_queue(path, queue())
            server = make_server(path, 0, "test-token")
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            base = f"http://127.0.0.1:{server.server_port}"
            def request(endpoint, body=None, token="test-token", origin=None):
                headers = {"X-Kicho-Token": token, "Content-Type": "application/json"}
                if origin:
                    headers["Origin"] = origin
                data = json.dumps(body).encode() if body is not None else None
                return urllib.request.urlopen(urllib.request.Request(base + endpoint, data=data, headers=headers), timeout=3)
            try:
                with self.assertRaises(urllib.error.HTTPError) as error:
                    request("/api/queue", token="")
                self.assertEqual(error.exception.code, 401)
                with request("/api/queue") as result:
                    row = json.load(result)["rows"][0]
                body = {"draft_id": row["draft_id"], "revision": row["revision"]}
                with self.assertRaises(urllib.error.HTTPError) as error:
                    request("/api/confirm", body, origin="https://outside.example")
                self.assertEqual(error.exception.code, 403)
                with request("/api/confirm", body) as result:
                    self.assertTrue(json.load(result)["ok"])
                with request("/api/export", {}) as result:
                    batch = json.load(result)
                with request("/api/exports/" + batch["batch_id"]) as result:
                    csv_bytes = result.read()
                self.assertTrue(csv_bytes.startswith(b"\xef\xbb\xbf"))
                self.assertEqual(len(list(csv.DictReader(io.StringIO(csv_bytes.decode("utf-8-sig"))))), 1)
                with self.assertRaises(urllib.error.HTTPError):
                    request("/api/export", {})
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=3)


if __name__ == "__main__":
    unittest.main()
