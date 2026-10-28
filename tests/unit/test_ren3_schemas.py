import pytest
from pydantic import ValidationError

from app.schemas import PropertyCreate, PropertyUpdate, TenantCreate, TenantUpdate

pytestmark = pytest.mark.jira("REN-3")


def _fields(exc: pytest.ExceptionInfo[ValidationError]) -> set[str]:
    return {".".join(str(p) for p in e["loc"]) for e in exc.value.errors()}


def test_ac5_property_create_requires_name_and_address():
    with pytest.raises(ValidationError) as exc:
        PropertyCreate.model_validate({})
    assert _fields(exc) == {"name", "address"}


@pytest.mark.parametrize(
    ("model", "payload", "field"),
    [
        (PropertyCreate, {"name": "   ", "address": "1 Elm St"}, "name"),
        (PropertyCreate, {"name": "x" * 201, "address": "1 Elm St"}, "name"),
        (PropertyCreate, {"name": "Elm", "address": "y" * 501}, "address"),
        (TenantCreate, {"full_name": "", "email": "a@example.com"}, "full_name"),
        (TenantCreate, {"full_name": "Ann", "email": "a@example.com", "phone": "9" * 51}, "phone"),
    ],
)
def test_ac5_blank_or_too_long_strings_rejected(model, payload, field):
    with pytest.raises(ValidationError) as exc:
        model.model_validate(payload)
    assert field in _fields(exc)


@pytest.mark.parametrize("email", ["no-at", "a@", "@b.com"])
def test_ac5_invalid_email_rejected(email):
    with pytest.raises(ValidationError) as exc:
        TenantCreate(full_name="Ann", email=email)
    assert _fields(exc) == {"email"}
    with pytest.raises(ValidationError) as exc:
        TenantUpdate(email=email)
    assert _fields(exc) == {"email"}


@pytest.mark.parametrize(
    ("model", "field"),
    [
        (PropertyUpdate, "name"),
        (PropertyUpdate, "address"),
        (TenantUpdate, "full_name"),
        (TenantUpdate, "email"),
    ],
)
def test_ac5_update_rejects_explicit_null_for_required_fields(model, field):
    with pytest.raises(ValidationError) as exc:
        model.model_validate({field: None})
    assert _fields(exc) == {field}


def test_ac5_strings_are_trimmed():
    prop = PropertyCreate(name="  Elm House ", address=" 1 Elm St")
    assert (prop.name, prop.address) == ("Elm House", "1 Elm St")
