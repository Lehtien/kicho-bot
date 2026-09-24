"""Create clearly synthetic receipt texts, extracted inputs, and separate expectations."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent / "fixtures" / "receipts"
CLIENT = {
    "client_id": "synthetic-demo-only",
    "business_type": "sole_proprietor",
    "industry": "Web制作・事務用品の小規模販売（架空事業）",
    "account_policy": (
        "以下はテスト用の架空事業の社内ルール。事務用品は消耗品費、販売目的の商品は仕入高。"
        "同じ購入先でも用途で区別する。電車・タクシーは旅費交通費、携帯回線は通信費、"
        "電気は水道光熱費、事業用書籍は新聞図書費、広告出稿は広告宣伝費、"
        "Web実装の業務委託は外注費、事務所家賃は地代家賃、振込手数料は支払手数料。"
        "カード払いの支出は未払金_カード、現金払いは現金、口座払いは普通預金。"
        "支払前の業務委託請求書は未払金。現金で受領した制作売上は借方現金・貸方売上高。"
        "事業カードでの私用購入は事業主貸・対象外とし、人が確認する。"
        "飲食は相手と業務目的を確認してから処理する。情報不足なら人が確認する。"
        "10万円以上の機器購入は、この社内ルールでは必ず用途・資産処理を人が確認する。"
        "金額や日付が読めない、税率混在、印字金額の計算不一致、内容が不明な証憑も人が確認する。"
    ),
    "frequent_vendors": {"こもれび文具店（架空）": "supplies", "青空モバイル（架空）": "comm"},
}


def case(case_id, title, vendor, items, total, net, tax, payment="cash", *,
         debit="supplies", credit=None, category="taxable_10", review=False,
         printed_date="2026-09-10", rate="0.10", note="", source="receipt", direction="expense",
         synced=False, unpaid=False, raw_override=None):
    credit = credit or {"cash": "cash", "credit_card": "card_payable", "bank": "ordinary_deposit", "unknown": "unknown_needs_review"}[payment]
    if unpaid:
        credit = "accrued"
    extracted = {
        "source_type": source, "transaction_type": direction, "vendor": vendor,
        "date": printed_date, "currency": "JPY", "amount_incl_tax": total,
        "amount_excl_tax": net, "tax_amount": tax, "tax_rate_hint": rate,
        "invoice_number": f"TEST-{case_id}", "qualified_invoice": "yes",
        "payment_method": payment,
        "items": [{"name": name, "amount_incl_tax": amount, "qty": 1} for name, amount in items],
        "needs_ocr_review": total is None or printed_date is None,
        "extraction_notes": [note] if note else [],
    }
    lines = ["【架空データ・テスト専用／実在する取引ではありません】", vendor, "請求書" if unpaid else "領収書",
             f"番号 TEST-{case_id}", "日付 " + (printed_date or "2026/09/??（かすれ）"),
             "宛名 架空スタジオ こはる", "--------------------------------"]
    lines.extend(f"{name}　{amount:,}円" if amount is not None else f"{name}　[判読不能]" for name, amount in items)
    lines += ["--------------------------------", f"合計 {total:,}円" if total is not None else "合計 [印字かすれで読めない]",
              f"税抜 {net:,}円" if net is not None else "税抜内訳の印字なし",
              f"消費税 {tax:,}円" if tax is not None else "消費税額の印字なし",
              "お支払い " + ("銀行振込・未払い／支払期限2026-09-30" if unpaid else {"cash": "現金", "credit_card": "事業用カード", "bank": "事業用銀行口座", "unknown": "不明"}[payment])]
    if note:
        lines.append("利用者メモ: " + note)
    extracted["raw_text"] = raw_override or "\n".join(lines)
    context = {
        "source_status": "synced_statement" if synced else "receipt_only",
        "statement_id": f"SYNTHETIC-STMT-{case_id}" if synced else None,
        "settlement_status": "unpaid" if unpaid else "paid",
        "wallet_key": None if unpaid else {"cash": "cash", "credit_card": "demo-card", "bank": "demo-bank", "unknown": None}[payment],
        "payment_date": None if unpaid else printed_date,
        "due_date": "2026-09-30" if unpaid else None,
        "item": "",
    }
    expected = {"debit": debit if isinstance(debit, list) else [debit],
                "credit": credit if isinstance(credit, list) else [credit],
                "tax": category if isinstance(category, list) else [category],
                "route": ["review" if review else "candidate_auto"]}
    return {"id": case_id, "title": title, "document": {"extracted": extracted, "client": CLIENT, "freee_context": context},
            "expected": expected, "scenario": note or title}


def build_cases():
    return [
        case("01-stationery", "事務用ノートとペン", "こもれび文具店（架空）", [("業務用ノート3冊", 660), ("油性ボールペン2本", 440)], 1100, 1000, 100, note="社内で使う事務用品。現金払い。"),
        case("02-train", "客先訪問の電車代", "東都レール（架空）", [("中央町→青葉台 片道乗車券", 440)], 440, 400, 40, debit="travel", note="制作案件の打ち合わせで客先へ移動。"),
        case("03-taxi-synced", "同期済みカードのタクシー", "つばめ交通（架空）", [("駅前→客先ビル 運賃", 2750)], 2750, 2500, 250, "credit_card", debit="travel", synced=True, note="客先訪問。カード明細はfreeeに同期済み。"),
        case("04-mobile", "業務専用の携帯回線", "青空モバイル（架空）", [("2026年9月 業務専用回線料金", 6380)], 6380, 5800, 580, "bank", debit="comm", synced=True),
        case("05-electricity", "事務所の電気料金", "みどり電力（架空）", [("事務所9月使用分 電気料金", 9240)], 9240, 8400, 840, "bank", debit="utilities", synced=True, note="住居とは別の事務所専用メーター。"),
        case("06-book", "業務用の技術書", "灯台書房（架空）", [("Webアクセシビリティ実務書", 3520)], 3520, 3200, 320, debit="software", note="受託制作の調査に使う書籍。"),
        case("07-advertising", "集客用の広告出稿", "青空広告プラットフォーム（架空）", [("自社サービス検索広告 9月配信分", 16500)], 16500, 15000, 1500, "credit_card", debit="advertising", synced=True),
        case("08-outsourcing-unpaid", "未払いの外注請求書", "合同会社ゆき実装（架空）", [("顧客サイトHTML実装 業務委託料", 55000)], 55000, 50000, 5000, "bank", debit="outsourcing", source="invoice", unpaid=True, note="納品検収済み。9月30日に支払予定、まだ振り込んでいない。"),
        case("09-office-rent", "専用事務所の家賃", "ひなた不動産（架空）", [("青葉ビル201 事務所賃料9月分", 88000)], 88000, 80000, 8000, "bank", debit="rent", synced=True, note="住宅ではなく事務所専用。"),
        case("10-bank-fee", "振込手数料", "こはる銀行（架空）", [("外注先への振込手数料", 330)], 330, 300, 30, "bank", debit="fees", synced=True, source="statement"),
        case("11-resale", "いつもの文具店だが販売用仕入", "こもれび文具店（架空）", [("販売用A5ノート まとめ仕入20冊", 6600)], 6600, 6000, 600, "credit_card", debit="purchases", synced=True, note="社内消費ではなく、自社ネットショップで販売する商品。"),
        case("12-personal", "事業カードで私用の買い物", "もりのマート（架空）", [("自宅用スナックと飲料", 1080)], 1080, 1000, 80, "credit_card", debit=["owner_draw", "unknown_needs_review"], category=["out_of_scope", "mixed_or_unknown"], review=True, rate="0.08", synced=True, note="家族の自宅用。事業と無関係だが、誤って事業カードで支払った。"),
        case("13-dining-unclear", "飲食の相手・目的が不明", "食堂あかり（架空）", [("ランチセット2名", 3300)], 3300, 3000, 300, debit=["entertainment", "unknown_needs_review", "owner_draw"], review=True, note="同席者と業務目的を記録しておらず、仕事か私用か確認が必要。"),
        case("14-mixed-tax", "8%食品と10%文具が混在", "にじいろストア（架空）", [("取引先への持ち帰り菓子（8%）", 1080), ("社内使用ボールペン（10%）", 220)], 1300, 1200, 100, debit=["supplies", "entertainment", "unknown_needs_review"], category="mixed_or_unknown", review=True, rate="mixed", note="8%対象1,080円・税80円、10%対象220円・税20円。用途も異なるため分割確認。"),
        case("15-amount-unreadable", "感熱紙が薄く金額不明", "こもれび文具店（架空）", [("コピー用紙 A4", None)], None, None, None, debit=["supplies", "unknown_needs_review"], category=["taxable_10", "mixed_or_unknown"], review=True, rate="unknown", note="商品名は読めるが、金額欄と税額欄が薄く判読不能。"),
        case("16-date-unreadable", "日付が破れて読めない", "つばめ交通（架空）", [("客先訪問タクシー運賃", 2200)], 2200, 2000, 200, debit="travel", review=True, printed_date=None, note="領収書右上が破れて日付を特定できない。"),
        case("17-tax-mismatch", "印字金額の計算不一致", "こもれび文具店（架空）", [("業務用ファイル10冊", 3300)], 3300, 3000, 500, debit="supplies", review=True, note="合計3,300円、税抜3,000円、税500円と読める。転記ミスか原本の印字を再確認。"),
        case("18-expensive-laptop", "高額パソコンの資産判断", "つばさ電機（架空）", [("制作業務用ノートパソコン", 186780)], 186780, 169800, 16980, "credit_card", debit=["tools", "unknown_needs_review"], review=True, synced=True, note="初めて購入する機種。社内ルールに従い用途と資産処理を人が確認する。"),
        case("19-vague", "新規取引先の品目が『品代』", "山の手商店（架空）", [("品代", 8800)], 8800, 8000, 800, debit="unknown_needs_review", review=True, note="何を購入したのか記録がなく、初めて使う店。"),
        case("20-cash-income", "制作代金を現金で受領", "株式会社あおい企画（架空）", [("Webバナー制作代金 受領分", 22000)], 22000, 20000, 2000, debit="cash", credit="sales", direction="income", note="当事業があおい企画へ発行した領収書の控え。制作を納品し、現金22,000円を受領した。"),
    ]


def main():
    from sys import path
    path.insert(0, str(Path(__file__).resolve().parents[1] / "kicho-bot/scripts"))
    from schemas import ExtractedDocument
    cases = build_cases()
    (ROOT / "inputs").mkdir(parents=True, exist_ok=True)
    (ROOT / "receipts").mkdir(exist_ok=True)
    manifest = {"synthetic": True, "description": "全件架空。実データの精度評価ではなく、社内ルールに対する動作確認用。", "cases": []}
    for entry in cases:
        ExtractedDocument.model_validate(entry["document"])
        relative = f"inputs/{entry['id']}.json"
        (ROOT / relative).write_text(json.dumps(entry["document"], ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        (ROOT / "receipts" / (entry["id"] + ".txt")).write_text(entry["document"]["extracted"]["raw_text"] + "\n", encoding="utf-8")
        manifest["cases"].append({"id": entry["id"], "title": entry["title"], "input": relative,
                                   "scenario": entry["scenario"], "expected": entry["expected"]})
    (ROOT / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Created and schema-validated {len(cases)} synthetic receipts at {ROOT}")


if __name__ == "__main__":
    main()
