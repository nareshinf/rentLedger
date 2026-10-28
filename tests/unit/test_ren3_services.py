from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError

from app.models import Lease, Property, Tenant
from app.schemas import PropertyCreate, PropertyUpdate, TenantCreate, TenantUpdate
from app.services import properties, tenants
from app.services.errors import ConflictError, NotFoundError

pytestmark = pytest.mark.jira("REN-3")


def _property(session, name="Elm House", address="1 Elm St"):
    return properties.create_property(session, PropertyCreate(name=name, address=address))


def _tenant(session, full_name="Ann Lee", email="ann@example.com", phone=None):
    return tenants.create_tenant(
        session, TenantCreate(full_name=full_name, email=email, phone=phone)
    )


def _lease(session, tenant, prop):
    session.add(
        Lease(
            tenant_id=tenant.id,
            property_id=prop.id,
            start_date=date(2026, 1, 1),
            monthly_rent=Decimal("1000.00"),
            due_day=1,
        )
    )
    session.commit()


def test_ac1_create_property_assigns_id(db_session):
    prop = _property(db_session)
    assert prop.id is not None
    assert (prop.name, prop.address) == ("Elm House", "1 Elm St")


def test_ac2_create_tenant_with_and_without_phone(db_session):
    without = _tenant(db_session)
    with_phone = _tenant(db_session, email="bo@example.com", phone="555-0100")
    assert without.id is not None and without.phone is None
    assert with_phone.phone == "555-0100"


def test_ac2_tenant_email_is_lowercased(db_session):
    assert _tenant(db_session, email="Ann.Lee@Example.COM").email == "ann.lee@example.com"


def test_ac3_list_returns_rows_in_id_order(db_session):
    a, b = _property(db_session, name="A"), _property(db_session, name="B")
    t1, t2 = _tenant(db_session), _tenant(db_session, email="b@example.com")
    assert [p.id for p in properties.list_properties(db_session)] == [a.id, b.id]
    assert [t.id for t in tenants.list_tenants(db_session)] == [t1.id, t2.id]


def test_ac3_get_returns_row(db_session):
    prop, tenant = _property(db_session), _tenant(db_session)
    assert properties.get_property(db_session, prop.id).name == "Elm House"
    assert tenants.get_tenant(db_session, tenant.id).email == "ann@example.com"


def test_ac4_update_changes_only_sent_fields(db_session):
    prop = _property(db_session)
    updated = properties.update_property(db_session, prop.id, PropertyUpdate(name="Oak House"))
    assert (updated.name, updated.address) == ("Oak House", "1 Elm St")

    tenant = _tenant(db_session, phone="555-0100")
    updated = tenants.update_tenant(db_session, tenant.id, TenantUpdate(email="NEW@example.com"))
    assert (updated.full_name, updated.email, updated.phone) == (
        "Ann Lee",
        "new@example.com",
        "555-0100",
    )


def test_ac4_tenant_phone_can_be_cleared(db_session):
    tenant = _tenant(db_session, phone="555-0100")
    assert tenants.update_tenant(db_session, tenant.id, TenantUpdate(phone=None)).phone is None


@pytest.mark.parametrize(
    "call",
    [
        lambda s: properties.get_property(s, 999),
        lambda s: properties.update_property(s, 999, PropertyUpdate(name="X")),
        lambda s: properties.delete_property(s, 999),
        lambda s: tenants.get_tenant(s, 999),
        lambda s: tenants.update_tenant(s, 999, TenantUpdate(full_name="X")),
        lambda s: tenants.delete_tenant(s, 999),
    ],
    ids=["get-prop", "update-prop", "delete-prop", "get-tenant", "update-tenant", "delete-tenant"],
)
def test_ac6_get_update_delete_unknown_id_raise_not_found(db_session, call):
    with pytest.raises(NotFoundError, match="999 not found"):
        call(db_session)


def test_ac7_delete_referenced_property_raises_conflict_and_keeps_row(db_session):
    prop, tenant = _property(db_session), _tenant(db_session)
    _lease(db_session, tenant, prop)
    with pytest.raises(ConflictError, match="referenced by a lease"):
        properties.delete_property(db_session, prop.id)
    assert db_session.get(Property, prop.id) is not None


def test_ac7_delete_referenced_tenant_raises_conflict_and_keeps_row(db_session):
    prop, tenant = _property(db_session), _tenant(db_session)
    _lease(db_session, tenant, prop)
    with pytest.raises(ConflictError, match="referenced by a lease"):
        tenants.delete_tenant(db_session, tenant.id)
    assert db_session.get(Tenant, tenant.id) is not None


def test_ac7_fk_restrict_blocks_raw_delete(db_session):
    prop, tenant = _property(db_session), _tenant(db_session)
    _lease(db_session, tenant, prop)
    with pytest.raises(IntegrityError):
        db_session.execute(delete(Property).where(Property.id == prop.id))
        db_session.commit()


def test_ac7_delete_unreferenced_removes_row(db_session):
    prop, tenant = _property(db_session), _tenant(db_session)
    properties.delete_property(db_session, prop.id)
    tenants.delete_tenant(db_session, tenant.id)
    assert db_session.scalars(select(Property)).all() == []
    assert db_session.scalars(select(Tenant)).all() == []
