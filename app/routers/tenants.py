from typing import Annotated

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from app.db import get_session
from app.schemas import TenantCreate, TenantRead, TenantUpdate
from app.services import tenants

router = APIRouter(prefix="/tenants", tags=["tenants"])
SessionDep = Annotated[Session, Depends(get_session)]


@router.post("", response_model=TenantRead, status_code=status.HTTP_201_CREATED)
def create_tenant(body: TenantCreate, session: SessionDep):
    return tenants.create_tenant(session, body)


@router.get("", response_model=list[TenantRead])
def list_tenants(session: SessionDep):
    return tenants.list_tenants(session)


@router.get("/{tenant_id}", response_model=TenantRead)
def get_tenant(tenant_id: int, session: SessionDep):
    return tenants.get_tenant(session, tenant_id)


@router.patch("/{tenant_id}", response_model=TenantRead)
def update_tenant(tenant_id: int, body: TenantUpdate, session: SessionDep):
    return tenants.update_tenant(session, tenant_id, body)


@router.delete("/{tenant_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_tenant(tenant_id: int, session: SessionDep) -> Response:
    tenants.delete_tenant(session, tenant_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
