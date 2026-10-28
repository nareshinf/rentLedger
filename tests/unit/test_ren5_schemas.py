from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.schemas import PaymentCreate, money_str

pytestmark = pytest.mark.jira("REN-5")

VALID = {"amount": "500.00", "paid_on": "2026-02-01"}


def _fields(exc: pytest.ExceptionInfo[ValidationError]) -> set[str]:
    return {".".join(str(p) for p in e["loc"]) for e in exc.value.errors()}


def test_ac1_payment_create_optional_method_and_note():
    bare = PaymentCreate.model_validate(VALID)
    assert (bare.method, bare.note) == (None, None)
    full = PaymentCreate.model_validate({**VALID, "method": "bank transfer", "note": "Feb rent"})
    assert (full.method, full.note) == ("bank transfer", "Feb rent")


@pytest.mark.parametrize(
    ("field", "value", "ok"),
    [
        ("method", "  cash  ", "cash"),
        ("method", "m" * 51, None),
        ("method", "   ", None),
        ("note", "n" * 501, None),
    ],
)
def test_ac1_method_and_note_trimmed_and_length_limited(field, value, ok):
    if ok is None:
        with pytest.raises(ValidationError) as exc:
            PaymentCreate.model_validate({**VALID, field: value})
        assert _fields(exc) == {field}
    else:
        assert getattr(PaymentCreate.model_validate({**VALID, field: value}), field) == ok


@pytest.mark.parametrize("amount", [0, -5, "10.005"])
def test_ac2_amount_must_be_positive_two_decimals(amount):
    with pytest.raises(ValidationError) as exc:
        PaymentCreate.model_validate({**VALID, "amount": amount})
    assert _fields(exc) == {"amount"}


def test_ac2_paid_on_required():
    with pytest.raises(ValidationError) as exc:
        PaymentCreate.model_validate({"amount": "10.00"})
    assert _fields(exc) == {"paid_on"}


@pytest.mark.parametrize(
    ("value", "text"),
    [
        (Decimal("1234.5"), "1234.50"),
        (Decimal("-300"), "-300.00"),
        (Decimal("0"), "0.00"),
        (Decimal("8641.92"), "8641.92"),
    ],
)
def test_ac8_money_str_formats_exactly(value, text):
    assert money_str(value) == text
