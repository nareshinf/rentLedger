from datetime import date
from decimal import Decimal

import pytest

from app.schemas import LeaseCreate, PropertyCreate, TenantCreate
from app.services import leases, properties, tenants
from app.services.errors import (
    ConflictError,
    NotFoundError,
    ReferenceNotFoundError,
    RuleViolationError,
)

pytestmark = pytest.mark.jira("REN-4")


@pytest.fixture
def refs(db_session):
    t1 = tenants.create_tenant(db_session, TenantCreate(full_name="Ann", email="a@example.com"))
    t2 = tenants.create_tenant(db_session, TenantCreate(full_name="Bo", email="b@example.com"))
    p1 = properties.create_property(db_session, PropertyCreate(name="Elm", address="1 Elm St"))
    p2 = properties.create_property(db_session, PropertyCreate(name="Oak", address="2 Oak St"))
    return {"t1": t1.id, "t2": t2.id, "p1": p1.id, "p2": p2.id}


def _lease(session, tenant_id, property_id, start, end=None, rent="1200.00", due_day=1):
    return leases.create_lease(
        session,
        LeaseCreate(
            tenant_id=tenant_id,
            property_id=property_id,
            start_date=start,
            end_date=end,
            monthly_rent=rent,
            due_day=due_day,
        ),
    )


def test_ac1_create_lease_is_active_with_exact_rent(db_session, refs):
    lease = _lease(db_session, refs["t1"], refs["p1"], date(2026, 1, 1), rent="1234.56")
    assert lease.id is not None
    assert lease.status == "active"
    assert lease.monthly_rent == Decimal("1234.56")


@pytest.mark.parametrize(
    ("tenant_ok", "property_ok", "missing"),
    [
        (False, True, {"tenant_id"}),
        (True, False, {"property_id"}),
        (False, False, {"tenant_id", "property_id"}),
    ],
)
def test_ac2_missing_tenant_property_or_both_raise_reference_error(
    db_session, refs, tenant_ok, property_ok, missing
):
    with pytest.raises(ReferenceNotFoundError) as exc:
        _lease(
            db_session,
            refs["t1"] if tenant_ok else 999,
            refs["p1"] if property_ok else 999,
            date(2026, 1, 1),
        )
    assert set(exc.value.missing) == missing


EXISTING = (date(2026, 3, 1), date(2026, 6, 30))


@pytest.mark.parametrize(
    ("start", "end", "conflict"),
    [
        (date(2026, 1, 1), date(2026, 2, 28), False),  # entirely before
        (date(2026, 7, 1), date(2026, 9, 30), False),  # entirely after / adjacent
        (date(2026, 1, 1), date(2026, 3, 1), True),  # ends on existing start (inclusive)
        (date(2026, 6, 30), date(2026, 8, 31), True),  # starts on existing end (inclusive)
        (date(2026, 2, 1), date(2026, 4, 1), True),  # overlaps start
        (date(2026, 6, 1), date(2026, 8, 1), True),  # overlaps end
        (date(2026, 4, 1), date(2026, 5, 1), True),  # inside
        (date(2026, 1, 1), date(2026, 12, 31), True),  # covers
        (date(2026, 1, 1), None, True),  # open-ended, starts before
    ],
)
def test_ac4_overlap_matrix(db_session, refs, start, end, conflict):
    _lease(db_session, refs["t1"], refs["p1"], *EXISTING)
    if conflict:
        with pytest.raises(ConflictError, match="overlaps lease"):
            _lease(db_session, refs["t2"], refs["p1"], start, end)
    else:
        assert _lease(db_session, refs["t2"], refs["p1"], start, end).status == "active"


def test_ac4_open_ended_existing_lease_blocks_any_later_start(db_session, refs):
    _lease(db_session, refs["t1"], refs["p1"], date(2026, 1, 1))
    with pytest.raises(ConflictError):
        _lease(db_session, refs["t2"], refs["p1"], date(2030, 1, 1), date(2030, 12, 31))


def test_ac4_open_ended_new_lease_overlaps_later_existing(db_session, refs):
    _lease(db_session, refs["t1"], refs["p1"], date(2027, 1, 1), date(2027, 12, 31))
    with pytest.raises(ConflictError):
        _lease(db_session, refs["t2"], refs["p1"], date(2026, 1, 1))


def test_ac4_other_property_never_conflicts(db_session, refs):
    _lease(db_session, refs["t1"], refs["p1"], *EXISTING)
    assert _lease(db_session, refs["t1"], refs["p2"], *EXISTING).property_id == refs["p2"]


def test_ac4_ended_lease_still_blocks_its_covered_period(db_session, refs):
    first = _lease(db_session, refs["t1"], refs["p1"], date(2026, 1, 1))
    leases.end_lease(db_session, first.id, date(2026, 6, 30))
    with pytest.raises(ConflictError):
        _lease(db_session, refs["t2"], refs["p1"], date(2026, 6, 1), date(2026, 12, 31))


def test_ac4_ended_lease_frees_dates_after_its_end(db_session, refs):
    first = _lease(db_session, refs["t1"], refs["p1"], date(2026, 1, 1))
    leases.end_lease(db_session, first.id, date(2026, 6, 30))
    assert _lease(db_session, refs["t2"], refs["p1"], date(2026, 7, 1)).status == "active"


def test_ac5_list_filters_by_tenant_property_and_both(db_session, refs):
    a = _lease(db_session, refs["t1"], refs["p1"], date(2026, 1, 1))
    b = _lease(db_session, refs["t1"], refs["p2"], date(2026, 1, 1), date(2026, 12, 31))
    c = _lease(db_session, refs["t2"], refs["p2"], date(2027, 1, 1))

    def ids(**kw):
        return [lease.id for lease in leases.list_leases(db_session, **kw)]

    assert ids() == [a.id, b.id, c.id]
    assert ids(tenant_id=refs["t1"]) == [a.id, b.id]
    assert ids(property_id=refs["p2"]) == [b.id, c.id]
    assert ids(tenant_id=refs["t1"], property_id=refs["p2"]) == [b.id]


def test_ac5_unknown_filter_id_returns_empty(db_session, refs):
    _lease(db_session, refs["t1"], refs["p1"], date(2026, 1, 1))
    assert leases.list_leases(db_session, tenant_id=999) == []
    assert leases.list_leases(db_session, property_id=999) == []


def test_ac6_end_lease_sets_status_and_end_date(db_session, refs):
    lease = _lease(db_session, refs["t1"], refs["p1"], date(2026, 1, 1))
    ended = leases.end_lease(db_session, lease.id, date(2026, 6, 30))
    assert (ended.status, ended.end_date) == ("ended", date(2026, 6, 30))
    assert leases.get_lease(db_session, lease.id).status == "ended"


def test_ac6_end_already_ended_raises_conflict(db_session, refs):
    lease = _lease(db_session, refs["t1"], refs["p1"], date(2026, 1, 1))
    leases.end_lease(db_session, lease.id, date(2026, 6, 30))
    with pytest.raises(ConflictError, match="already ended"):
        leases.end_lease(db_session, lease.id, date(2026, 5, 31))


def test_ac6_end_before_start_raises_rule_violation(db_session, refs):
    lease = _lease(db_session, refs["t1"], refs["p1"], date(2026, 1, 1))
    with pytest.raises(RuleViolationError) as exc:
        leases.end_lease(db_session, lease.id, date(2025, 12, 31))
    assert exc.value.field == "end_date"
    assert leases.get_lease(db_session, lease.id).status == "active"


def test_ac6_end_later_than_existing_end_raises_rule_violation(db_session, refs):
    lease = _lease(db_session, refs["t1"], refs["p1"], date(2026, 1, 1), date(2026, 12, 31))
    with pytest.raises(RuleViolationError, match="later than the current end date"):
        leases.end_lease(db_session, lease.id, date(2027, 1, 31))
    assert leases.end_lease(db_session, lease.id, date(2026, 12, 31)).status == "ended"


def test_ac6_end_unknown_id_raises_not_found(db_session):
    with pytest.raises(NotFoundError, match="Lease 999 not found"):
        leases.end_lease(db_session, 999, date(2026, 1, 1))
