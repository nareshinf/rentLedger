from sqlalchemy import exists, select
from sqlalchemy.orm import Session

from app.models import Lease, Property
from app.schemas import PropertyCreate, PropertyUpdate
from app.services.errors import ConflictError, NotFoundError


def create_property(session: Session, data: PropertyCreate) -> Property:
    prop = Property(**data.model_dump())
    session.add(prop)
    session.commit()
    session.refresh(prop)
    return prop


def list_properties(session: Session) -> list[Property]:
    return list(session.scalars(select(Property).order_by(Property.id)))


def get_property(session: Session, property_id: int) -> Property:
    prop = session.get(Property, property_id)
    if prop is None:
        raise NotFoundError("Property", property_id)
    return prop


def update_property(session: Session, property_id: int, data: PropertyUpdate) -> Property:
    prop = get_property(session, property_id)
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(prop, field, value)
    session.commit()
    session.refresh(prop)
    return prop


def delete_property(session: Session, property_id: int) -> None:
    prop = get_property(session, property_id)
    if session.scalar(select(exists().where(Lease.property_id == property_id))):
        raise ConflictError(f"Property {property_id} is referenced by a lease")
    session.delete(prop)
    session.commit()
