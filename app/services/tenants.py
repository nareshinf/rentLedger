from sqlalchemy import exists, select
from sqlalchemy.orm import Session

from app.models import Lease, Tenant
from app.schemas import TenantCreate, TenantUpdate
from app.services.errors import ConflictError, NotFoundError


def create_tenant(session: Session, data: TenantCreate) -> Tenant:
    tenant = Tenant(**data.model_dump())
    session.add(tenant)
    session.commit()
    session.refresh(tenant)
    return tenant


def list_tenants(session: Session) -> list[Tenant]:
    return list(session.scalars(select(Tenant).order_by(Tenant.id)))


def get_tenant(session: Session, tenant_id: int) -> Tenant:
    tenant = session.get(Tenant, tenant_id)
    if tenant is None:
        raise NotFoundError("Tenant", tenant_id)
    return tenant


def update_tenant(session: Session, tenant_id: int, data: TenantUpdate) -> Tenant:
    tenant = get_tenant(session, tenant_id)
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(tenant, field, value)
    session.commit()
    session.refresh(tenant)
    return tenant


def delete_tenant(session: Session, tenant_id: int) -> None:
    tenant = get_tenant(session, tenant_id)
    if session.scalar(select(exists().where(Lease.tenant_id == tenant_id))):
        raise ConflictError(f"Tenant {tenant_id} is referenced by a lease")
    session.delete(tenant)
    session.commit()
