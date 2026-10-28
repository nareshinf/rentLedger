from datetime import date
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    StringConstraints,
    ValidationInfo,
    field_serializer,
    field_validator,
)

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
Address = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]
Phone = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=50)]
Money = Annotated[Decimal, Field(gt=0, max_digits=12, decimal_places=2)]
DueDay = Annotated[int, Field(ge=1, le=28)]
LeaseStatus = Literal["active", "ended"]


def _reject_null(value):
    if value is None:
        raise ValueError("may not be null")
    return value


def _lower(value: str | None) -> str | None:
    return value.lower() if value is not None else None


class HealthResponse(BaseModel):
    status: Literal["ok"]


class PropertyCreate(BaseModel):
    name: Name
    address: Address


class PropertyUpdate(BaseModel):
    name: Name | None = None
    address: Address | None = None

    _not_null = field_validator("name", "address", mode="before")(_reject_null)


class PropertyRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    address: str


class TenantCreate(BaseModel):
    full_name: Name
    email: EmailStr
    phone: Phone | None = None

    _lower_email = field_validator("email")(_lower)


class TenantUpdate(BaseModel):
    full_name: Name | None = None
    email: EmailStr | None = None
    phone: Phone | None = None

    _not_null = field_validator("full_name", "email", mode="before")(_reject_null)
    _lower_email = field_validator("email")(_lower)


class TenantRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    full_name: str
    email: str
    phone: str | None


class LeaseCreate(BaseModel):
    tenant_id: int
    property_id: int
    start_date: date
    end_date: date | None = None
    monthly_rent: Money
    due_day: DueDay

    @field_validator("end_date")
    @classmethod
    def _end_not_before_start(cls, end_date: date | None, info: ValidationInfo) -> date | None:
        start_date = info.data.get("start_date")
        if end_date is not None and start_date is not None and end_date < start_date:
            raise ValueError("end_date must be on or after start_date")
        return end_date


class LeaseEnd(BaseModel):
    end_date: date


class LeaseRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tenant_id: int
    property_id: int
    start_date: date
    end_date: date | None
    monthly_rent: Decimal
    due_day: int
    status: LeaseStatus

    @field_serializer("monthly_rent")
    def _money(self, value: Decimal) -> str:
        return f"{value:.2f}"
