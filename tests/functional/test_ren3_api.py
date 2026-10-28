from datetime import date
from decimal import Decimal

import pytest

from app.models import Lease

pytestmark = pytest.mark.jira("REN-3")

PROPERTY = {"name": "Elm House", "address": "1 Elm St"}
TENANT = {"full_name": "Ann Lee", "email": "ann@example.com"}


def _create(client, path, payload):
    response = client.post(path, json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def _add_lease(app, tenant_id, property_id):
    with app.state.session_factory() as session:
        session.add(
            Lease(
                tenant_id=tenant_id,
                property_id=property_id,
                start_date=date(2026, 1, 1),
                monthly_rent=Decimal("1000.00"),
                due_day=1,
            )
        )
        session.commit()


def _error_fields(response):
    return {e["field"] for e in response.json()["errors"]}


def test_ac1_post_property_returns_201_with_id(client):
    response = client.post("/properties", json=PROPERTY)
    assert response.status_code == 201
    body = response.json()
    assert isinstance(body["id"], int)
    assert body == {"id": body["id"], **PROPERTY}


def test_ac2_post_tenant_returns_201_with_id(client):
    without_phone = client.post("/tenants", json=TENANT)
    assert without_phone.status_code == 201
    assert without_phone.json() == {"id": without_phone.json()["id"], **TENANT, "phone": None}

    with_phone = client.post(
        "/tenants", json={**TENANT, "email": "bo@example.com", "phone": "555-0100"}
    )
    assert with_phone.status_code == 201
    assert with_phone.json()["phone"] == "555-0100"
    assert with_phone.json()["id"] != without_phone.json()["id"]


def test_ac3_list_and_get_tenants(client):
    first = _create(client, "/tenants", TENANT)
    second = _create(client, "/tenants", {**TENANT, "email": "bo@example.com"})

    listed = client.get("/tenants")
    assert listed.status_code == 200
    assert listed.json() == [first, second]

    one = client.get(f"/tenants/{second['id']}")
    assert one.status_code == 200
    assert one.json() == second


def test_ac3_list_and_get_properties(client):
    first = _create(client, "/properties", PROPERTY)
    second = _create(client, "/properties", {**PROPERTY, "name": "Oak House"})

    listed = client.get("/properties")
    assert listed.status_code == 200
    assert listed.json() == [first, second]

    one = client.get(f"/properties/{first['id']}")
    assert one.status_code == 200
    assert one.json() == first


def test_ac4_patch_property_then_get_reflects_change(client):
    prop = _create(client, "/properties", PROPERTY)
    response = client.patch(f"/properties/{prop['id']}", json={"address": "2 Oak Ave"})
    assert response.status_code == 200
    assert response.json() == {**prop, "address": "2 Oak Ave"}
    assert client.get(f"/properties/{prop['id']}").json()["address"] == "2 Oak Ave"


def test_ac4_patch_tenant_then_get_reflects_change(client):
    tenant = _create(client, "/tenants", TENANT)
    response = client.patch(
        f"/tenants/{tenant['id']}", json={"full_name": "Ann Smith", "phone": "555-0199"}
    )
    assert response.status_code == 200
    assert client.get(f"/tenants/{tenant['id']}").json() == {
        **tenant,
        "full_name": "Ann Smith",
        "phone": "555-0199",
    }


def test_ac5_post_tenant_missing_full_name_returns_400(client):
    response = client.post("/tenants", json={"email": "ann@example.com"})
    assert response.status_code == 400
    assert "full_name" in _error_fields(response)


def test_ac5_post_tenant_invalid_email_returns_400(client):
    response = client.post("/tenants", json={**TENANT, "email": "not-an-email"})
    assert response.status_code == 400
    assert _error_fields(response) == {"email"}


def test_ac5_post_property_missing_fields_returns_400_naming_both(client):
    response = client.post("/properties", json={})
    assert response.status_code == 400
    assert _error_fields(response) == {"name", "address"}


def test_ac5_patch_with_invalid_email_returns_400(client):
    tenant = _create(client, "/tenants", TENANT)
    response = client.patch(f"/tenants/{tenant['id']}", json={"email": "bad@"})
    assert response.status_code == 400
    assert _error_fields(response) == {"email"}
    assert client.get(f"/tenants/{tenant['id']}").json()["email"] == TENANT["email"]


@pytest.mark.parametrize("resource", ["tenants", "properties"])
@pytest.mark.parametrize("method", ["get", "patch", "delete"])
def test_ac6_unknown_id_returns_404(client, resource, method):
    kwargs = {"json": {}} if method == "patch" else {}
    response = client.request(method.upper(), f"/{resource}/999", **kwargs)
    assert response.status_code == 404
    assert "999 not found" in response.json()["detail"]


@pytest.mark.parametrize("resource", ["tenants", "properties"])
def test_ac6_non_integer_id_returns_400(client, resource):
    response = client.get(f"/{resource}/abc")
    assert response.status_code == 400


def test_ac7_delete_referenced_property_returns_409_and_keeps_record(app, client):
    prop = _create(client, "/properties", PROPERTY)
    tenant = _create(client, "/tenants", TENANT)
    _add_lease(app, tenant["id"], prop["id"])

    response = client.delete(f"/properties/{prop['id']}")
    assert response.status_code == 409
    assert "referenced by a lease" in response.json()["detail"]
    assert client.get(f"/properties/{prop['id']}").status_code == 200


def test_ac7_delete_referenced_tenant_returns_409_and_keeps_record(app, client):
    prop = _create(client, "/properties", PROPERTY)
    tenant = _create(client, "/tenants", TENANT)
    _add_lease(app, tenant["id"], prop["id"])

    response = client.delete(f"/tenants/{tenant['id']}")
    assert response.status_code == 409
    assert client.get(f"/tenants/{tenant['id']}").status_code == 200


@pytest.mark.parametrize(("resource", "payload"), [("tenants", TENANT), ("properties", PROPERTY)])
def test_ac7_delete_unreferenced_returns_204_then_404(client, resource, payload):
    record = _create(client, f"/{resource}", payload)
    response = client.delete(f"/{resource}/{record['id']}")
    assert response.status_code == 204
    assert response.content == b""
    assert client.get(f"/{resource}/{record['id']}").status_code == 404
