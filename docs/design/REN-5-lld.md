# REN-5 — Payments and balance: Low-Level Design

- **Issue:** [REN-5](https://nareshmalhotra.atlassian.net/browse/REN-5)
- **HLD:** [REN-5-hld.md](REN-5-hld.md) (`hld-approved`; P1–P4 recommendations accepted)
- **Stage:** LLD (awaiting `lld-approved`)

## 1. Files

| Path | Change |
|------|--------|
| `app/models.py` | new `Payment` |
| `app/schemas.py` | `PaymentCreate`, `PaymentRead`, `BalanceRead`; shared `money_str()` helper (also used by `LeaseRead`) |
| `app/services/payments.py` | **new**: `create_payment`, `list_payments` |
| `app/services/balance.py` | **new**: `Balance` dataclass and `compute_balance` |
| `app/routers/payments.py` | **new**: payments and balance endpoints under `/leases/{lease_id}` |
| `app/main.py` | include the payments router |
| `tests/conftest.py` | add `fixed_today` fixture (overrides `get_clock` with `FixedClock`) |
| `tests/unit/test_ren5_*.py`, `tests/functional/test_ren5_api.py` | tests (§6) |
| `README.md` | payments and balance endpoints, and the balance formula |

## 2. Model (`app/models.py`)

```python
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
```

## 3. Schemas (`app/schemas.py`)

```python
Method = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=50)]
Note = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]


def money_str(value: Decimal) -> str:  # f"{value:.2f}"; "-300.00" for credit
    ...


class PaymentCreate(BaseModel):
    amount: Money  # reuses REN-4 Money: > 0, ≤ 2 dp
    paid_on: date
    method: Method | None = None
    note: Note | None = None


class PaymentRead(BaseModel):  # from_attributes
    id: int
    lease_id: int
    amount: Decimal
    paid_on: date
    method: str | None
    note: str | None
    # field_serializer("amount") → money_str


class BalanceRead(BaseModel):  # from_attributes (built from Balance)
    lease_id: int
    as_of: date
    monthly_rent: Decimal
    charges_due: int
    charged: Decimal
    paid: Decimal
    balance: Decimal
    # field_serializer("monthly_rent", "charged", "paid", "balance") → money_str
```
`LeaseRead._money` switches to `money_str`. The output is the same.

## 4. Services

### `app/services/payments.py`
```python
def create_payment(session, lease_id: int, data: PaymentCreate, today: date) -> Payment
    # leases.get_lease(session, lease_id)                          → 404 (AC3); ended leases allowed (P1)
    # if data.paid_on > today: RuleViolationError("paid_on", "paid_on cannot be in the future")  (P2)
    # Payment(lease_id=lease_id, **data.model_dump()); add; commit; refresh

def list_payments(session, lease_id: int) -> list[Payment]
    # leases.get_lease(...)                                         → 404
    # ORDER BY paid_on, id                                          (AC4)
```
`today` is a plain argument: the router passes `clock.today()`, so the service never reads the clock.

### `app/services/balance.py`
```python
@dataclass(frozen=True)
class Balance:
    lease_id: int; as_of: date; monthly_rent: Decimal; charges_due: int
    charged: Decimal; paid: Decimal; balance: Decimal

CENT = Decimal("0.01")

def compute_balance(session, lease_id: int, as_of: date) -> Balance
    # lease = leases.get_lease(session, lease_id)                   → 404
    # n = len(due_dates(lease.start_date, lease.end_date, lease.due_day, through=as_of))
    # charged = (lease.monthly_rent * n).quantize(CENT)
    # amounts = session.scalars(select(Payment.amount).where(lease_id ==, paid_on <= as_of))
    # paid = sum(amounts, Decimal("0")).quantize(CENT)              # Python Decimal sum, not SQL SUM
    # return Balance(..., balance=(charged - paid).quantize(CENT))
```

## 5. Router (`app/routers/payments.py`)

`APIRouter(prefix="/leases", tags=["payments"])`, with
`ClockDep = Annotated[Clock, Depends(get_clock)]`.

| Endpoint | Signature | Status / model |
|----------|-----------|----------------|
| `POST /leases/{lease_id}/payments` | `body: PaymentCreate`, `clock: ClockDep` | 201, `PaymentRead` |
| `GET /leases/{lease_id}/payments` | — | 200, `list[PaymentRead]` |
| `GET /leases/{lease_id}/balance` | `as_of: Annotated[date \| None, Query(alias="asOf")] = None`, `clock: ClockDep` | 200, `BalanceRead` |

The balance uses `as_of or clock.today()`. `?asOf=2026-13-01` → 400 with `field: "asOf"`, through the REN-2 handler.
FastAPI validates the body before the handler runs, so an invalid body on an unknown lease → 400, not 404.

## 6. Test plan

All tests are marked `@pytest.mark.jira("REN-5")`.

**`tests/conftest.py`: `fixed_today` fixture.** It sets `app.dependency_overrides[get_clock]` to return
`FixedClock(date(2026, 4, 15))` and removes the override afterwards. Unit tests pass `today` / `as_of` explicitly.

**Unit: `tests/unit/test_ren5_schemas.py`**

| AC | Test |
|----|------|
| AC1 | `test_ac1_payment_create_optional_method_and_note`; `test_ac1_method_and_note_trimmed_and_length_limited` |
| AC2 | `test_ac2_amount_must_be_positive_two_decimals` (parametrised: `0`, `-5`, `"10.005"`); `test_ac2_paid_on_required` |
| AC8 | `test_ac8_money_str_formats_exactly` (`Decimal("1234.5")` → `"1234.50"`, `Decimal("-300")` → `"-300.00"`) |

**Unit: `tests/unit/test_ren5_services.py`** (using `db_session` and a lease fixture: start 2026-01-01, rent 1200.00, due day 1)

| AC | Test |
|----|------|
| AC1 | `test_ac1_create_payment_returns_row`; `test_ac1_payment_on_ended_lease_allowed` (P1) |
| AC2 | `test_ac2_future_paid_on_rejected` (P2: today + 1 → `RuleViolationError("paid_on")`); `test_ac2_paid_on_today_allowed` |
| AC3 | `test_ac3_unknown_lease_raises_not_found` (create, list, balance) |
| AC4 | `test_ac4_list_ordered_by_date_then_id` (inserted out of order, same-day pair) |
| AC5 | `test_ac5_balance_is_due_count_times_rent_minus_paid` (as_of 2026-04-15 → N=4, charged 4800.00, paid 4500.00, balance 300.00) |
| AC5 | `test_ac5_ended_lease_stops_charging_at_end_date` |
| AC6 | `test_ac6_overpayment_gives_negative_balance` |
| AC7 | `test_ac7_as_of_counts_due_dates_and_payments_on_that_day`; `test_ac7_as_of_excludes_later_charges_and_payments`; `test_ac7_as_of_before_start_charges_nothing` |
| AC8 | `test_ac8_cents_sum_exactly` (rent 1234.56 × 7 = 8641.92; 100 × 0.01 = 1.00; 0.10 + 0.20 + 0.30 = 0.60, read back from SQLite) |

**Functional: `tests/functional/test_ren5_api.py`**

| AC | Test | Asserts |
|----|------|---------|
| AC1 | `test_ac1_post_payment_returns_201` | 201; `{id, lease_id, amount: "500.00", paid_on, method, note}` |
| AC1 | `test_ac1_payment_on_ended_lease_returns_201` | 201 (P1) |
| AC2 | `test_ac2_invalid_payment_returns_400` (parametrised: amount 0 / −1 / missing `paid_on` / future `paid_on`) | 400; field named |
| AC3 | `test_ac3_unknown_lease_returns_404` (parametrised: POST payments / GET payments / GET balance) | 404 |
| AC4 | `test_ac4_list_payments_in_date_order` | `paid_on` ascending |
| AC5 | `test_ac5_balance_defaults_to_today` (`fixed_today`) | exact `charges_due`, `charged`, `paid`, `balance` strings |
| AC6 | `test_ac6_overpayment_shows_negative_balance` | `balance` = `"-…"` |
| AC7 | `test_ac7_balance_as_of_date`; `test_ac7_invalid_as_of_returns_400` | the subset only; 400 with field `asOf` |
| AC8 | `test_ac8_cent_payments_balance_exactly` | `paid: "0.60"`, `balance` exact |

Order: write the tests, run them, and confirm they fail. Then implement. The REN-2, REN-3 and REN-4 suites must keep passing,
and coverage must stay ≥ 90%.

## 7. Documentation

`README.md`: add the payment and balance rows to the API table, and the balance formula with the `asOf` meaning.
