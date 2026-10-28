import pytest

pytestmark = pytest.mark.jira("REN-5")


@pytest.fixture
def lease_id(client):
    tenant = client.post("/tenants", json={"full_name": "Ann", "email": "a@example.com"}).json()
    prop = client.post("/properties", json={"name": "Elm", "address": "1 Elm St"}).json()
    response = client.post(
        "/leases",
        json={
            "tenant_id": tenant["id"],
            "property_id": prop["id"],
            "start_date": "2026-01-01",
            "monthly_rent": "1200.00",
            "due_day": 1,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def _pay(client, lease_id, amount, paid_on, **extra):
    response = client.post(
        f"/leases/{lease_id}/payments", json={"amount": amount, "paid_on": paid_on, **extra}
    )
    assert response.status_code == 201, response.text
    return response.json()


def _fields(response):
    return {e["field"] for e in response.json()["errors"]}


def test_ac1_post_payment_returns_201(client, fixed_today, lease_id):
    response = client.post(
        f"/leases/{lease_id}/payments",
        json={"amount": 500, "paid_on": "2026-02-01", "method": "cash", "note": "Feb rent"},
    )
    assert response.status_code == 201
    body = response.json()
    assert isinstance(body["id"], int)
    assert body == {
        "id": body["id"],
        "lease_id": lease_id,
        "amount": "500.00",
        "paid_on": "2026-02-01",
        "method": "cash",
        "note": "Feb rent",
    }


def test_ac1_payment_on_ended_lease_returns_201(client, fixed_today, lease_id):
    client.post(f"/leases/{lease_id}/end", json={"end_date": "2026-02-28"})
    assert _pay(client, lease_id, "100.00", "2026-04-01")["amount"] == "100.00"


@pytest.mark.parametrize(
    ("payload", "field"),
    [
        ({"amount": 0, "paid_on": "2026-02-01"}, "amount"),
        ({"amount": "-1", "paid_on": "2026-02-01"}, "amount"),
        ({"amount": "10.00"}, "paid_on"),
        ({"amount": "10.00", "paid_on": "2026-04-16"}, "paid_on"),  # future (P2)
    ],
)
def test_ac2_invalid_payment_returns_400(client, fixed_today, lease_id, payload, field):
    response = client.post(f"/leases/{lease_id}/payments", json=payload)
    assert response.status_code == 400
    assert _fields(response) == {field}


@pytest.mark.parametrize(
    ("method", "path", "body"),
    [
        ("POST", "/leases/999/payments", {"amount": "10.00", "paid_on": "2026-02-01"}),
        ("GET", "/leases/999/payments", None),
        ("GET", "/leases/999/balance", None),
    ],
)
def test_ac3_unknown_lease_returns_404(client, fixed_today, method, path, body):
    response = client.request(method, path, json=body)
    assert response.status_code == 404
    assert "Lease 999 not found" in response.json()["detail"]


def test_ac4_list_payments_in_date_order(client, fixed_today, lease_id):
    for paid_on in ("2026-03-01", "2026-01-05", "2026-02-01"):
        _pay(client, lease_id, "10.00", paid_on)
    response = client.get(f"/leases/{lease_id}/payments")
    assert response.status_code == 200
    assert [p["paid_on"] for p in response.json()] == ["2026-01-05", "2026-02-01", "2026-03-01"]


def test_ac5_balance_defaults_to_today(client, fixed_today, lease_id):
    for paid_on in ("2026-01-03", "2026-02-03", "2026-03-03"):
        _pay(client, lease_id, "1500.00", paid_on)
    response = client.get(f"/leases/{lease_id}/balance")
    assert response.status_code == 200
    assert response.json() == {
        "lease_id": lease_id,
        "as_of": "2026-04-15",
        "monthly_rent": "1200.00",
        "charges_due": 4,
        "charged": "4800.00",
        "paid": "4500.00",
        "balance": "300.00",
    }


def test_ac6_overpayment_shows_negative_balance(client, fixed_today, lease_id):
    _pay(client, lease_id, "5000.00", "2026-01-02")
    body = client.get(f"/leases/{lease_id}/balance").json()
    assert body["balance"] == "-200.00"


def test_ac7_balance_as_of_date(client, fixed_today, lease_id):
    _pay(client, lease_id, "1200.00", "2026-01-03")
    _pay(client, lease_id, "1200.00", "2026-03-02")
    body = client.get(f"/leases/{lease_id}/balance", params={"asOf": "2026-02-28"}).json()
    assert (body["as_of"], body["charges_due"]) == ("2026-02-28", 2)
    assert (body["charged"], body["paid"], body["balance"]) == ("2400.00", "1200.00", "1200.00")


def test_ac7_invalid_as_of_returns_400(client, fixed_today, lease_id):
    response = client.get(f"/leases/{lease_id}/balance", params={"asOf": "2026-13-01"})
    assert response.status_code == 400
    assert _fields(response) == {"asOf"}


def test_ac8_cent_payments_balance_exactly(client, fixed_today, lease_id):
    for amount in ("0.10", "0.20", "0.30"):
        _pay(client, lease_id, amount, "2026-01-02")
    body = client.get(f"/leases/{lease_id}/balance", params={"asOf": "2026-01-31"}).json()
    assert (body["charged"], body["paid"], body["balance"]) == ("1200.00", "0.60", "1199.40")
