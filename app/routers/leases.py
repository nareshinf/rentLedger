from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.db import get_session
from app.schemas import LeaseCreate, LeaseEnd, LeaseRead
from app.services import leases

router = APIRouter(prefix="/leases", tags=["leases"])
SessionDep = Annotated[Session, Depends(get_session)]


@router.post("", response_model=LeaseRead, status_code=status.HTTP_201_CREATED)
def create_lease(body: LeaseCreate, session: SessionDep):
    return leases.create_lease(session, body)


@router.get("", response_model=list[LeaseRead])
def list_leases(
    session: SessionDep,
    tenant_id: Annotated[int | None, Query(alias="tenantId")] = None,
    property_id: Annotated[int | None, Query(alias="propertyId")] = None,
):
    return leases.list_leases(session, tenant_id=tenant_id, property_id=property_id)


@router.get("/{lease_id}", response_model=LeaseRead)
def get_lease(lease_id: int, session: SessionDep):
    return leases.get_lease(session, lease_id)


@router.post("/{lease_id}/end", response_model=LeaseRead)
def end_lease(lease_id: int, body: LeaseEnd, session: SessionDep):
    return leases.end_lease(session, lease_id, body.end_date)
