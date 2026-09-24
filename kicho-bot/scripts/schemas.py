"""Validate receipt input, charts, and TypeSafe-compatible answers."""
from __future__ import annotations

from datetime import date
from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_validator

Probability = Annotated[float, Field(ge=0, le=1)]
Yen = Annotated[int, Field(ge=0)]
Text = Annotated[str, Field(min_length=1)]


class StrictModel(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", allow_inf_nan=False)


class Item(StrictModel):
    name: Text
    amount_incl_tax: Yen | None = None
    qty: Annotated[float, Field(gt=0)] | None = None


class Extracted(StrictModel):
    source_type: Literal["receipt", "invoice", "statement", "handwritten", "unknown"]
    transaction_type: Literal["expense", "income", "unknown"] = "expense"
    vendor: Text | None
    date: str | None
    currency: Literal["JPY"]
    amount_incl_tax: Yen | None
    amount_excl_tax: Yen | None = None
    tax_amount: Yen | None = None
    tax_rate_hint: Literal["0.10", "0.08", "mixed", "unknown"]
    invoice_number: str | None = None
    qualified_invoice: Literal["yes", "no", "unknown"]
    payment_method: Literal["cash", "credit_card", "bank", "e_money", "unknown"]
    items: list[Item]
    raw_text: str
    needs_ocr_review: bool
    extraction_notes: list[str] = Field(default_factory=list)

    @field_validator("vendor")
    @classmethod
    def nonblank_vendor(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("vendor must not be blank")
        return value

    @field_validator("date")
    @classmethod
    def calendar_date(cls, value: str | None) -> str | None:
        if value is not None and date.fromisoformat(value).isoformat() != value:
            raise ValueError("date must use YYYY-MM-DD")
        return value


class Client(StrictModel):
    model_config = ConfigDict(strict=True, extra="allow", allow_inf_nan=False)
    business_type: str | None = None
    industry: str | None = None
    account_policy: str | None = None
    frequent_vendors: dict[str, str] = Field(default_factory=dict)
    client_id: Text | None = None


class FreeeContext(StrictModel):
    source_status: Literal["receipt_only", "synced_statement", "unknown"] = "unknown"
    statement_id: Text | None = None
    settlement_status: Literal["paid", "unpaid", "unknown"] = "unknown"
    wallet_key: Text | None = None
    payment_date: str | None = None
    due_date: str | None = None
    item: str = ""

    @field_validator("payment_date", "due_date")
    @classmethod
    def calendar_date(cls, value: str | None) -> str | None:
        return Extracted.calendar_date(value)


class ExtractedDocument(StrictModel):
    extracted: Extracted
    client: Client = Field(default_factory=Client)
    history_hints: dict[str, JsonValue] = Field(default_factory=dict)
    freee_context: FreeeContext = Field(default_factory=FreeeContext)


class Account(StrictModel):
    id: Text
    name: Text
    when_to_use: str | None = None
    side_hint: str | None = None


class Chart(StrictModel):
    chart_id: Text
    note: str | None = None
    debit_accounts: Annotated[list[Account], Field(min_length=2, max_length=255)]
    credit_accounts: Annotated[list[Account], Field(min_length=2, max_length=255)]

    @field_validator("debit_accounts", "credit_accounts")
    @classmethod
    def account_ids(cls, accounts: list[Account]) -> list[Account]:
        ids = [account.id for account in accounts]
        if len(ids) != len(set(ids)) or "unknown_needs_review" not in ids:
            raise ValueError("account IDs must be unique and include unknown_needs_review")
        return accounts


class AnswerModel(StrictModel):
    model_config = ConfigDict(strict=True, extra="allow", allow_inf_nan=False)


class ChoiceAnswer(AnswerModel):
    type: Literal["choice"]
    choice: Text
    confidence: Probability
    probabilities: dict[str, Probability]


class NoulAnswer(AnswerModel):
    type: Literal["noul"]
    noul: Probability


class ScoreAnswer(AnswerModel):
    type: Literal["score"]
    score: Annotated[float, Field(ge=0, le=3)]
    confidence: Probability
    probabilities: dict[str, Probability]
    legend: dict[str, str]


class Answers(AnswerModel):
    debit_account: ChoiceAnswer
    credit_account: ChoiceAnswer
    tax_category: ChoiceAnswer
    matches_client_rule: NoulAnswer
    unusual: NoulAnswer
    review_priority: ScoreAnswer


class JevResponse(AnswerModel):
    model: Text
    answers: Answers
    usage: dict[str, Annotated[int, Field(ge=0)]]


def validate_response(result: object, payload: dict) -> dict:
    validated = JevResponse.model_validate(result).model_dump()
    for name, question in payload["questions"].items():
        answer = validated["answers"][name]
        if question["type"] == "noul":
            continue
        probabilities = answer["probabilities"]
        expected = (set(question["criteria"]) if question["type"] == "choice"
                    else {str(i) for i in range(len(question["criteria"]))})
        if set(probabilities) != expected or abs(sum(probabilities.values()) - 1) > 0.001:
            raise ValueError("invalid answer probabilities")
        if question["type"] == "choice" and answer["choice"] not in expected:
            raise ValueError("answer is outside the supplied chart")
    return validated
