from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.schemas import LeaseCreate, PaymentCreate, PropertyCreate, TenantCreate
from app.services import balance, leases, payments, properties, tenants
from app.services.errors import NotFoundError, RuleViolationError

pytestmark = pytest.mark.jira("REN-5")

TODAY = date(2026, 4, 15)


@pytest.fixture
def lease(db_session):
    return _new_lease(db_session, "a@example.com", "Elm", start=date(2026, 1, 1), rent="1200.00")


def _new_lease(session, email, prop_name, start, rent, end=None):
    tenant = tenants.create_tenant(session, TenantCreate(full_name="T", email=email))
    prop = properties.create_property(session, PropertyCreate(name=prop_name, address="1 St"))
    return leases.create_lease(
        session,
        LeaseCreate(
            tenant_id=tenant.id,
            property_id=prop.id,
            start_date=start,
            end_date=end,
            monthly_rent=rent,
            due_day=1,
        ),
    )


def _pay(session, lease_id, amount, paid_on, today=TODAY, **extra):
    return payments.create_payment(
        session, lease_id, PaymentCreate(amount=amount, paid_on=paid_on, **extra), today=today
    )


def test_ac1_create_payment_returns_row(db_session, lease):
    payment = _pay(db_session, lease.id, "500.00", date(2026, 2, 1), method="cash", note="Feb")
    assert payment.id is not None
    assert (payment.lease_id, payment.amount, payment.paid_on) == (
        lease.id,
        Decimal("500.00"),
        date(2026, 2, 1),
    )
    assert (payment.method, payment.note) == ("cash", "Feb")


def test_ac1_payment_on_ended_lease_allowed(db_session, lease):
    leases.end_lease(db_session, lease.id, date(2026, 2, 28))
    assert _pay(db_session, lease.id, "100.00", date(2026, 4, 1)).lease_id == lease.id


def test_ac2_future_paid_on_rejected(db_session, lease):
    with pytest.raises(RuleViolationError) as exc:
        _pay(db_session, lease.id, "10.00", TODAY + timedelta(days=1))
    assert exc.value.field == "paid_on"
    assert payments.list_payments(db_session, lease.id) == []


def test_ac2_paid_on_today_allowed(db_session, lease):
    assert _pay(db_session, lease.id, "10.00", TODAY).paid_on == TODAY


@pytest.mark.parametrize(
    "call",
    [
        lambda s: _pay(s, 999, "10.00", TODAY),
        lambda s: payments.list_payments(s, 999),
        lambda s: balance.compute_balance(s, 999, TODAY),
    ],
    ids=["create", "list", "balance"],
)
def test_ac3_unknown_lease_raises_not_found(db_session, call):
    with pytest.raises(NotFoundError, match="Lease 999 not found"):
        call(db_session)


def test_ac4_list_ordered_by_date_then_id(db_session, lease):
    late = _pay(db_session, lease.id, "1.00", date(2026, 3, 1))
    early = _pay(db_session, lease.id, "2.00", date(2026, 1, 5))
    same_a = _pay(db_session, lease.id, "3.00", date(2026, 2, 1))
    same_b = _pay(db_session, lease.id, "4.00", date(2026, 2, 1))
    listed = [p.id for p in payments.list_payments(db_session, lease.id)]
    assert listed == [early.id, same_a.id, same_b.id, late.id]


def test_ac5_balance_is_due_count_times_rent_minus_paid(db_session, lease):
    for month in (1, 2, 3):
        _pay(db_session, lease.id, "1500.00", date(2026, month, 3))
    result = balance.compute_balance(db_session, lease.id, TODAY)
    assert result.charges_due == 4  # Jan 1, Feb 1, Mar 1, Apr 1
    assert result.charged == Decimal("4800.00") == result.charges_due * result.monthly_rent
    assert result.paid == Decimal("4500.00")
    assert result.balance == Decimal("300.00")
    assert (result.lease_id, result.as_of) == (lease.id, TODAY)


def test_ac5_ended_lease_stops_charging_at_end_date(db_session, lease):
    leases.end_lease(db_session, lease.id, date(2026, 2, 15))
    result = balance.compute_balance(db_session, lease.id, date(2026, 12, 31))
    assert (result.charges_due, result.charged) == (2, Decimal("2400.00"))


def test_ac6_overpayment_gives_negative_balance(db_session, lease):
    _pay(db_session, lease.id, "5000.00", date(2026, 1, 2))
    assert balance.compute_balance(db_session, lease.id, TODAY).balance == Decimal("-200.00")


def test_ac7_as_of_counts_due_dates_and_payments_on_that_day(db_session, lease):
    _pay(db_session, lease.id, "1200.00", date(2026, 3, 1))
    result = balance.compute_balance(db_session, lease.id, date(2026, 3, 1))
    assert (result.charges_due, result.paid) == (3, Decimal("1200.00"))


def test_ac7_as_of_excludes_later_charges_and_payments(db_session, lease):
    _pay(db_session, lease.id, "1200.00", date(2026, 1, 3))
    _pay(db_session, lease.id, "1200.00", date(2026, 3, 2))
    result = balance.compute_balance(db_session, lease.id, date(2026, 2, 28))
    assert result.charges_due == 2
    assert (result.charged, result.paid, result.balance) == (
        Decimal("2400.00"),
        Decimal("1200.00"),
        Decimal("1200.00"),
    )


def test_ac7_as_of_before_start_charges_nothing(db_session):
    future = _new_lease(db_session, "f@example.com", "Oak", date(2026, 6, 1), "900.00")
    _pay(db_session, future.id, "900.00", date(2026, 4, 1))
    result = balance.compute_balance(db_session, future.id, date(2026, 5, 1))
    assert (result.charges_due, result.charged, result.balance) == (
        0,
        Decimal("0.00"),
        Decimal("-900.00"),
    )


def test_ac8_cents_sum_exactly(db_session):
    lease = _new_lease(db_session, "c@example.com", "Cent", date(2026, 1, 1), "1234.56")
    for amount in ("0.10", "0.20", "0.30"):
        _pay(db_session, lease.id, amount, date(2026, 1, 2))
    for _ in range(100):
        _pay(db_session, lease.id, "0.01", date(2026, 1, 3))
    db_session.expire_all()  # force amounts to be read back from SQLite

    result = balance.compute_balance(db_session, lease.id, date(2026, 7, 1))
    assert result.charges_due == 7
    assert result.charged == Decimal("8641.92")
    assert result.paid == Decimal("1.60")
    assert result.balance == Decimal("8640.32")
    assert 0.1 + 0.2 + 0.3 != 0.6  # the float trap this test guards against
