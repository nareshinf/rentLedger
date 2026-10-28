from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Lease, Property, Tenant
from app.schemas import LeaseCreate
from app.services.errors import (
    ConflictError,
    NotFoundError,
    ReferenceNotFoundError,
    RuleViolationError,
)


def create_lease(session: Session, data: LeaseCreate) -> Lease:
    missing = {}
    if session.get(Tenant, data.tenant_id) is None:
        missing["tenant_id"] = f"Tenant {data.tenant_id} does not exist"
    if session.get(Property, data.property_id) is None:
        missing["property_id"] = f"Property {data.property_id} does not exist"
    if missing:
        raise ReferenceNotFoundError(missing)

    clash = _find_overlap(session, data.property_id, data.start_date, data.end_date)
    if clash is not None:
        raise ConflictError(f"Lease overlaps lease {clash.id} on property {data.property_id}")

    lease = Lease(**data.model_dump(), status="active")
    session.add(lease)
    session.commit()
    session.refresh(lease)
    return lease


def _find_overlap(
    session: Session, property_id: int, start: date, end: date | None
) -> Lease | None:
    # Every lease on the property counts, active or ended (HLD decision D1).
    # Ranges are inclusive; a NULL end date is open-ended.
    query = select(Lease).where(
        Lease.property_id == property_id,
        (Lease.end_date.is_(None)) | (Lease.end_date >= start),
    )
    if end is not None:
        query = query.where(Lease.start_date <= end)
    return session.scalars(query.order_by(Lease.id).limit(1)).first()


def list_leases(
    session: Session, tenant_id: int | None = None, property_id: int | None = None
) -> list[Lease]:
    query = select(Lease).order_by(Lease.id)
    if tenant_id is not None:
        query = query.where(Lease.tenant_id == tenant_id)
    if property_id is not None:
        query = query.where(Lease.property_id == property_id)
    return list(session.scalars(query))


def get_lease(session: Session, lease_id: int) -> Lease:
    lease = session.get(Lease, lease_id)
    if lease is None:
        raise NotFoundError("Lease", lease_id)
    return lease


def end_lease(session: Session, lease_id: int, end_date: date) -> Lease:
    lease = get_lease(session, lease_id)
    if lease.status == "ended":
        raise ConflictError(f"Lease {lease_id} is already ended")
    if end_date < lease.start_date:
        raise RuleViolationError("end_date", "end_date must be on or after start_date")
    if lease.end_date is not None and end_date > lease.end_date:
        # HLD decision D2: ending can only keep or shorten the lease.
        raise RuleViolationError(
            "end_date", f"end_date cannot be later than the current end date {lease.end_date}"
        )
    lease.end_date = end_date
    lease.status = "ended"
    session.commit()
    session.refresh(lease)
    return lease
