#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["pydantic>=2.12,<3"]
# ///
"""One live Jev request per synthetic fixture; expected answers stay local."""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "kicho-bot"
FIXTURES = ROOT / "tests/fixtures/receipts"
sys.path.insert(0, str(SKILL / "scripts"))
from freee_deals import Draft


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate the synthetic receipts against the live configured Jev provider")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--provider", choices=("vercel", "typesafe"))
    parser.add_argument("--case", action="append", dest="case_ids", help="Run only this fixture ID; repeat for multiple cases")
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    manifest = json.loads((FIXTURES / "manifest.json").read_text(encoding="utf-8"))
    if args.case_ids:
        unknown = set(args.case_ids) - {case["id"] for case in manifest["cases"]}
        if unknown:
            parser.error("Unknown fixture ID")
        manifest["cases"] = [case for case in manifest["cases"] if case["id"] in args.case_ids]
    results = []
    for case in manifest["cases"]:
        command = [sys.executable, str(SKILL / "scripts/classify_journal.py"), str(FIXTURES / case["input"])]
        if args.provider:
            command += ["--provider", args.provider]
        row = {"id": case["id"], "title": case["title"], "expected": case["expected"]}
        try:
            process = subprocess.run(command, capture_output=True, text=True, timeout=45)
            if process.returncode:
                # No raw stderr: upstream errors may contain credentials or input data.
                http_error = re.search(r"Jevへの接続に失敗しました（HTTP (\d{3})）", process.stderr)
                error = ("http_" + http_error.group(1) if http_error else
                         "invalid_api_response" if "Jevの応答形式を検証できませんでした" in process.stderr else
                         "network_error" if "Jevと通信できません" in process.stderr else
                         f"classifier_exit_{process.returncode}")
                row.update(status="error", error=error)
            else:
                data = json.loads(process.stdout)
                Draft.model_validate(data)
                (args.out / f"{case['id']}.json").write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
                actual = {"debit": data["journal"]["debit"]["id"], "credit": data["journal"]["credit"]["id"],
                          "tax": data["journal"]["tax_category"], "route": data["route"]}
                checks = {key: actual[key] in allowed for key, allowed in case["expected"].items()}
                row.update(status="match" if all(checks.values()) else "difference", actual=actual, checks=checks,
                           provider=data["provider"], model=data["model"],
                           debit_name=data["journal"]["debit"]["name"], credit_name=data["journal"]["credit"]["name"],
                           debit_confidence=data["answers"]["debit_account"]["confidence"], usage=data["usage"])
        except subprocess.TimeoutExpired:
            row.update(status="error", error="timeout")
        except ValueError:
            row.update(status="error", error="invalid_response")
        results.append(row)
        print(f"{len(results):02d}/{len(manifest['cases'])} {row['id']}: {row['status']} {row.get('actual', {})}", flush=True)
        report = {"synthetic": True, "executed_at": datetime.now(timezone.utc).isoformat(), "results": results}
        (args.out / "results.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    successes = [row for row in results if row["status"] != "error"]
    matches = sum(row["status"] == "match" for row in results)
    reviews = sum(row["actual"]["route"] == "review" for row in successes)
    usage = {key: sum(row["usage"].get(key, 0) for row in successes) for key in ("input_tokens", "output_tokens")}
    lines = [f"# 架空領収書{len(results)}件の実APIテスト", "", "全件架空のテキストと抽出済みJSONです。画像OCRの評価や実データの分類精度を示すものではありません。",
             "期待値は呼び出し前に定義したテスト用社内ルールです。期待値そのものはJevに送っていません。", "",
             f"- 実API成功: {len(successes)}/{len(results)}件", f"- 期待した科目・税カテゴリ・routeの全項目に一致: {matches}/{len(results)}件",
             f"- review: {reviews}件 / candidate_auto: {len(successes) - reviews}件", f"- トークン合計: 入力{usage['input_tokens']:,} / 出力{usage['output_tokens']:,}",
             "- freeeへの登録・実データの確定は行っていません。", "", "| ケース | 借方 | 貸方 | 税カテゴリ | 振り分け | 期待値との差 |", "|---|---|---|---|---|---|"]
    for row in results:
        if row["status"] == "error":
            lines.append(f"| {row['title']} | — | — | — | エラー | {row['error']} |")
        else:
            differences = ", ".join(key for key, passed in row["checks"].items() if not passed) or "一致"
            lines.append(f"| [{row['title']}]({row['id']}.json) | {row['debit_name']} | {row['credit_name']} | {row['actual']['tax']} | {row['actual']['route']} | {differences} |")
    (args.out / "REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"api_success": len(successes), "cases": len(results), "matches": matches, "review": reviews, "usage": usage, "report": str(args.out / "REPORT.md")}, ensure_ascii=False), flush=True)
    return 1 if any(row["status"] == "error" for row in results) else 0


if __name__ == "__main__":
    raise SystemExit(main())
