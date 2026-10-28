import pytest

pytestmark = pytest.mark.jira("REN-4")


@pytest.fixture
def refs(client):
    def create(path, payload):
        response = client.post(path, json=payload)
        assert response.status_code == 201, response.text
        return response.json()["id"]

    return {
        "t1": create("/tenants", {"full_name": "Ann", "email": "a@example.com"}),
        "t2": create("/tenants", {"full_name": "Bo", "email": "b@example.com"}),
        "p1": create("/properties", {"name": "Elm", "address": "1 Elm St"}),
        "p2": create("/properties", {"name": "Oak", "address": "2 Oak St"}),
    }


def _payload(refs, tenant="t1", prop="p1", **overrides):
    return {
        "tenant_id": refs[tenant],
        "property_id": refs[prop],
        "start_date": "2026-01-01",
        "monthly_rent": "1200.00",
        "due_day": 1,
        **overrides,
    }


def _create(client, payload):
    response = client.post("/leases", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def _fields(response):
    return {e["field"] for e in response.json()["errors"]}


def test_ac1_post_lease_returns_201_active_with_id(client, refs):
    response = client.post("/leases", json=_payload(refs, end_date="2026-12-31", due_day=5))
    assert response.status_code == 201
    body = response.json()
    assert isinstance(body["id"], int)
    assert body == {
        "id": body["id"],
        "tenant_id": refs["t1"],
        "property_id": refs["p1"],
        "start_date": "2026-01-01",
        "end_date": "2026-12-31",
        "monthly_rent": "1200.00",
        "due_day": 5,
        "status": "active",
    }


def test_ac1_lease_with_past_end_date_starts_active(client, refs):
    body = _create(client, _payload(refs, start_date="2020-01-01", end_date="2020-12-31"))
    assert body["status"] == "active"


@pytest.mark.parametrize(
    ("tenant_id", "property_id", "expected"),
    [
        (999, None, {"tenant_id"}),
        (None, 999, {"property_id"}),
        (999, 999, {"tenant_id", "property_id"}),
    ],
)
def test_ac2_unknown_tenant_or_property_returns_422_naming_it(
    client, refs, tenant_id, property_id, expected
):
    payload = _payload(refs)
    if tenant_id:
        payload["tenant_id"] = tenant_id
    if property_id:
        payload["property_id"] = property_id
    response = client.post("/leases", json=payload)
    assert response.status_code == 422
    assert _fields(response) == expected
    assert all("999 does not exist" in e["message"] for e in response.json()["errors"])


@pytest.mark.parametrize(
    ("overrides", "field"),
    [
        ({"end_date": "2025-12-31"}, "end_date"),
        ({"monthly_rent": 0}, "monthly_rent"),
        ({"monthly_rent": "-1"}, "monthly_rent"),
        ({"due_day": 0}, "due_day"),
        ({"due_day": 29}, "due_day"),
    ],
)
def test_ac3_invalid_terms_return_400(client, refs, overrides, field):
    response = client.post("/leases", json=_payload(refs, **overrides))
    assert response.status_code == 400
    assert _fields(response) == {field}


def test_ac3_validation_runs_before_reference_check(client, refs):
    response = client.post("/leases", json={**_payload(refs, due_day=29), "tenant_id": 999})
    assert response.status_code == 400
    assert _fields(response) == {"due_day"}


def test_ac4_overlapping_lease_returns_409(client, refs):
    first = _create(client, _payload(refs, end_date="2026-06-30"))
    response = client.post("/leases", json=_payload(refs, tenant="t2", start_date="2026-06-30"))
    assert response.status_code == 409
    assert f"overlaps lease {first['id']}" in response.json()["detail"]


def test_ac4_adjacent_lease_returns_201(client, refs):
    _create(client, _payload(refs, end_date="2026-06-30"))
    response = client.post("/leases", json=_payload(refs, tenant="t2", start_date="2026-07-01"))
    assert response.status_code == 201


@pytest.fixture
def three_leases(client, refs):
    a = _create(client, _payload(refs, "t1", "p1"))
    b = _create(client, _payload(refs, "t1", "p2", end_date="2026-12-31"))
    c = _create(client, _payload(refs, "t2", "p2", start_date="2027-01-01"))
    return refs, a["id"], b["id"], c["id"]


def _ids(response):
    assert response.status_code == 200
    return [lease["id"] for lease in response.json()]


def test_ac5_filter_by_tenant_id(client, three_leases):
    refs, a, b, _ = three_leases
    assert _ids(client.get("/leases", params={"tenantId": refs["t1"]})) == [a, b]


def test_ac5_filter_by_property_id(client, three_leases):
    refs, _, b, c = three_leases
    assert _ids(client.get("/leases", params={"propertyId": refs["p2"]})) == [b, c]
    both = client.get("/leases", params={"tenantId": refs["t2"], "propertyId": refs["p2"]})
    assert _ids(both) == [c]


def test_ac5_no_filter_lists_all(client, three_leases):
    _, a, b, c = three_leases
    assert _ids(client.get("/leases")) == [a, b, c]


def test_ac5_non_integer_filter_returns_400(client):
    response = client.get("/leases", params={"tenantId": "abc"})
    assert response.status_code == 400
    assert _fields(response) == {"tenantId"}


def test_ac5_get_lease_by_id(client, refs):
    lease = _create(client, _payload(refs))
    response = client.get(f"/leases/{lease['id']}")
    assert response.status_code == 200
    assert response.json() == lease


def test_ac5_get_unknown_lease_returns_404(client):
    assert client.get("/leases/999").status_code == 404


def test_ac6_end_lease_returns_200_ended(client, refs):
    lease = _create(client, _payload(refs))
    response = client.post(f"/leases/{lease['id']}/end", json={"end_date": "2026-06-30"})
    assert response.status_code == 200
    expected = {**lease, "status": "ended", "end_date": "2026-06-30"}
    assert response.json() == expected
    assert client.get(f"/leases/{lease['id']}").json() == expected


def test_ac6_end_twice_returns_409(client, refs):
    lease = _create(client, _payload(refs))
    client.post(f"/leases/{lease['id']}/end", json={"end_date": "2026-06-30"})
    response = client.post(f"/leases/{lease['id']}/end", json={"end_date": "2026-05-31"})
    assert response.status_code == 409


def test_ac6_end_unknown_returns_404(client):
    assert client.post("/leases/999/end", json={"end_date": "2026-01-01"}).status_code == 404


def test_ac6_end_before_start_returns_400(client, refs):
    lease = _create(client, _payload(refs))
    response = client.post(f"/leases/{lease['id']}/end", json={"end_date": "2025-12-31"})
    assert response.status_code == 400
    assert _fields(response) == {"end_date"}


def test_ac6_end_later_than_existing_end_returns_400(client, refs):
    lease = _create(client, _payload(refs, end_date="2026-12-31"))
    response = client.post(f"/leases/{lease['id']}/end", json={"end_date": "2027-06-30"})
    assert response.status_code == 400
    assert _fields(response) == {"end_date"}


def test_ac6_end_missing_end_date_returns_400(client, refs):
    lease = _create(client, _payload(refs))
    response = client.post(f"/leases/{lease['id']}/end", json={})
    assert response.status_code == 400
    assert _fields(response) == {"end_date"}


@pytest.mark.parametrize("resource", ["tenants", "properties"])
def test_delete_tenant_or_property_with_full_lease_still_409(client, refs, resource):
    _create(client, _payload(refs))
    record_id = refs["t1"] if resource == "tenants" else refs["p1"]
    assert client.delete(f"/{resource}/{record_id}").status_code == 409
