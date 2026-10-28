from datetime import date
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.schemas import LeaseCreate, LeaseRead

pytestmark = pytest.mark.jira("REN-4")

VALID = {
    "tenant_id": 1,
    "property_id": 1,
    "start_date": "2026-01-01",
    "monthly_rent": "1200.00",
    "due_day": 1,
}


def _fields(exc: pytest.ExceptionInfo[ValidationError]) -> set[str]:
    return {".".join(str(p) for p in e["loc"]) for e in exc.value.errors()}


def _invalid(**overrides) -> set[str]:
    with pytest.raises(ValidationError) as exc:
        LeaseCreate.model_validate({**VALID, **overrides})
    return _fields(exc)


@pytest.mark.parametrize(
    ("value", "expected"),
    [(1200, Decimal("1200")), (1200.5, Decimal("1200.5")), ("1200.50", Decimal("1200.50"))],
)
def test_ac1_money_accepts_int_float_and_string_exactly(value, expected):
    assert LeaseCreate.model_validate({**VALID, "monthly_rent": value}).monthly_rent == expected


def test_ac1_lease_read_serialises_rent_as_two_decimal_string():
    lease = LeaseRead(
        id=1,
        tenant_id=1,
        property_id=1,
        start_date=date(2026, 1, 1),
        end_date=None,
        monthly_rent=Decimal("1200"),
        due_day=1,
        status="active",
    )
    assert lease.model_dump(mode="json")["monthly_rent"] == "1200.00"


def test_ac3_end_before_start_rejected():
    assert _invalid(end_date="2025-12-31") == {"end_date"}


def test_ac3_end_equal_start_allowed():
    lease = LeaseCreate.model_validate({**VALID, "end_date": "2026-01-01"})
    assert lease.end_date == lease.start_date


@pytest.mark.parametrize("rent", [0, -1, "1200.555"])
def test_ac3_rent_must_be_positive_with_two_decimals(rent):
    assert _invalid(monthly_rent=rent) == {"monthly_rent"}


@pytest.mark.parametrize("due_day", [0, 29, 31])
def test_ac3_due_day_outside_range_rejected(due_day):
    assert _invalid(due_day=due_day) == {"due_day"}


@pytest.mark.parametrize("due_day", [1, 28])
def test_ac3_due_day_bounds_allowed(due_day):
    assert LeaseCreate.model_validate({**VALID, "due_day": due_day}).due_day == due_day


def test_ac3_multiple_errors_reported_together():
    assert _invalid(end_date="2025-01-01", due_day=29, monthly_rent=0) == {
        "end_date",
        "due_day",
        "monthly_rent",
    }
