from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, StringConstraints, field_validator

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
Address = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]
Phone = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=50)]


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
