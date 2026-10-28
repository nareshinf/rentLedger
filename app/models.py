from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, ForeignKey, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class Property(Base):
    __tablename__ = "properties"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    address: Mapped[str] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class Tenant(Base):
    __tablename__ = "tenants"

    id: Mapped[int] = mapped_column(primary_key=True)
    full_name: Mapped[str] = mapped_column(String(200))
    email: Mapped[str] = mapped_column(String(320))
    phone: Mapped[str | None] = mapped_column(String(50))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class Lease(Base):
    __tablename__ = "leases"
    __table_args__ = (
        CheckConstraint("due_day BETWEEN 1 AND 28", name="ck_leases_due_day"),
        CheckConstraint("status IN ('active', 'ended')", name="ck_leases_status"),
        CheckConstraint("monthly_rent > 0", name="ck_leases_rent_positive"),
        CheckConstraint("end_date IS NULL OR end_date >= start_date", name="ck_leases_dates"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(
        ForeignKey("tenants.id", ondelete="RESTRICT"), index=True
    )
    property_id: Mapped[int] = mapped_column(
        ForeignKey("properties.id", ondelete="RESTRICT"), index=True
    )
    start_date: Mapped[date]
    end_date: Mapped[date | None]
    monthly_rent: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    due_day: Mapped[int]
    status: Mapped[str] = mapped_column(String(10), default="active")
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class Payment(Base):
    __tablename__ = "payments"
    __table_args__ = (CheckConstraint("amount > 0", name="ck_payments_amount_positive"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    lease_id: Mapped[int] = mapped_column(ForeignKey("leases.id", ondelete="RESTRICT"), index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    paid_on: Mapped[date]
    method: Mapped[str | None] = mapped_column(String(50))
    note: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
