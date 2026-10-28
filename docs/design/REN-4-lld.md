# REN-4 — Leases API: Low-Level Design

- **Issue:** [REN-4](https://nareshmalhotra.atlassian.net/browse/REN-4)
- **HLD:** [REN-4-hld.md](REN-4-hld.md) (`hld-approved`; D1–D4 recommendations accepted)
- **Stage:** LLD (awaiting `lld-approved`)

## 1. Files

| Path | Change |
|------|--------|
| `app/models.py` | `Lease` gains the term columns and CHECK constraints |
| `app/schemas.py` | `LeaseCreate`, `LeaseEnd`, `LeaseRead`; `Money` and `DueDay` types |
| `app/services/errors.py` | add `ReferenceNotFoundError` (→ 422) and `RuleViolationError` (→ 400) |
| `app/errors.py` | add `reference_not_found_handler`, `rule_violation_handler` |
| `app/services/leases.py` | **new**: create, list, get, end |
| `app/services/rent.py` | **new**: `due_dates()` |
| `app/routers/leases.py` | **new**: endpoints |
| `app/main.py` | register the two handlers and the leases router |
| `tests/unit/test_ren3_services.py`, `tests/functional/test_ren3_api.py` | lease helpers pass the now-required terms (test setup only, no REN-3 behaviour change) |
| `tests/unit/test_ren4_*.py`, `tests/functional/test_ren4_api.py` | new tests (§6) |
| `README.md` | lease endpoints in the API table and a "recreate your local DB" note |

## 2. Model (`app/models.py`)

```python
class Lease(Base):
    __tablename__ = "leases"
    __table_args__ = (
        CheckConstraint("due_day BETWEEN 1 AND 28", name="ck_leases_due_day"),
        CheckConstraint("status IN ('active', 'ended')", name="ck_leases_status"),
        CheckConstraint("monthly_rent > 0", name="ck_leases_rent_positive"),
        CheckConstraint("end_date IS NULL OR end_date >= start_date", name="ck_leases_dates"),
    )
    id, tenant_id, property_id  # unchanged from REN-3
    start_date: Mapped[date]
    end_date: Mapped[date | None]
    monthly_rent: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    due_day: Mapped[int]
    status: Mapped[str] = mapped_column(String(10), default="active")
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
```
**SQLite and `Numeric`:** SQLite has no exact decimal type and stores the value as REAL. Values up
to 12 digits with 2 decimal places (at most 15 significant digits) survive the round trip exactly, and SQLAlchemy
quantises them back to `Decimal` with 2 decimal places on read. SQLAlchemy prints an `SAWarning` about this
on SQLite, and it gets filtered in pytest config **only for that message**. On a server database `Numeric`
is exact. Code never sees a float.

## 3. Schemas (`app/schemas.py`)

```python
Money  = Annotated[Decimal, Field(gt=0, max_digits=12, decimal_places=2)]
DueDay = Annotated[int, Field(ge=1, le=28)]

class LeaseCreate(BaseModel):
    tenant_id: int
    property_id: int
    start_date: date
    end_date: date | None = None
    monthly_rent: Money
    due_day: DueDay
    # field_validator("end_date"): if start_date is in info.data and end_date < start_date
    #   → ValueError("end_date must be on or after start_date")   (loc = end_date)

class LeaseEnd(BaseModel):
    end_date: date

class LeaseRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id, tenant_id, property_id, start_date, end_date, monthly_rent: Decimal, due_day, status
    # field_serializer("monthly_rent") → f"{value:.2f}"   e.g. "1200.00"
```
- `monthly_rent` accepts `1200`, `1200.5`, `"1200.50"`. It rejects `0`, `-5` and `1200.555` → 400 `monthly_rent`.
- AC3 errors are reported together. For example, end < start and due day 29 → `errors` contains both `end_date` and `due_day`.

## 4. Services

### `app/services/errors.py` additions
```python
class ReferenceNotFoundError(Exception):
    def __init__(self, missing: dict[str, str]):   # {"tenant_id": "Tenant 9 does not exist", ...}
class RuleViolationError(Exception):
    def __init__(self, field: str, message: str)
```
Handlers in `app/errors.py`:
- `422 {"detail": "Referenced record not found", "errors": [{"field", "message"}, ...]}`
- `400 {"detail": "Validation failed", "errors": [{"field", "message"}]}`, the same shape as a REN-2 validation error

### `app/services/leases.py`
```python
def create_lease(session, data: LeaseCreate) -> Lease
    # 1. missing = {} ; Tenant/Property looked up with session.get → ReferenceNotFoundError(missing) if any
    # 2. clash = _find_overlap(session, data.property_id, data.start_date, data.end_date)
    #    → ConflictError(f"Lease overlaps lease {clash.id} on property {pid}")
    # 3. Lease(**data.model_dump(), status="active"); add; commit; refresh

def _find_overlap(session, property_id, start, end, exclude_id=None) -> Lease | None
    # D1: every lease on the property, active or ended. Inclusive ranges, NULL end = open-ended:
    # WHERE property_id = :pid
    #   AND (:end IS NULL OR start_date <= :end)
    #   AND (end_date IS NULL OR end_date >= :start)
    # ORDER BY id LIMIT 1

def list_leases(session, tenant_id: int | None = None, property_id: int | None = None) -> list[Lease]
    # optional filters, combined with AND; ORDER BY id

def get_lease(session, lease_id) -> Lease            # NotFoundError("Lease", id)

def end_lease(session, lease_id, end_date: date) -> Lease
    # lease = get_lease()                                → 404
    # lease.status == "ended"  → ConflictError("Lease <id> is already ended")   → 409
    # end_date < lease.start_date → RuleViolationError("end_date", "must be on or after start_date")
    # lease.end_date and end_date > lease.end_date      (D2)
    #     → RuleViolationError("end_date", "cannot be later than the current end date <d>")
    # lease.end_date = end_date; lease.status = "ended"; commit; refresh
```
`end_lease` only ever shortens the range, so it can't create an overlap and needs no re-check.

### `app/services/rent.py`
```python
def due_dates(start_date: date, end_date: date | None, due_day: int, through: date) -> list[date]
    # first = start_date.replace(day=due_day); if first < start_date: first = next month, same day
    # last  = min(through, end_date) if end_date else through
    # monthly steps from first while d <= last (due_day ≤ 28, so every month has the day)
```
It's a pure function: no session and no clock. The arguments are plain values, so REN-5 can call it with
`through = asOf` or with "today" from the injectable `Clock`.

## 5. Router (`app/routers/leases.py`)

| Endpoint | Signature | Status / model |
|----------|-----------|----------------|
| `POST /leases` | `body: LeaseCreate` | 201, `LeaseRead` |
| `GET /leases` | `tenant_id: Annotated[int \| None, Query(alias="tenantId")] = None`, same for `propertyId` | 200, `list[LeaseRead]` |
| `GET /leases/{lease_id}` | — | 200, `LeaseRead` |
| `POST /leases/{lease_id}/end` | `body: LeaseEnd` | 200, `LeaseRead` |

`?tenantId=abc` → 400 with `field: "tenantId"`, through the REN-2 handler.

## 6. Test plan

All tests are marked `@pytest.mark.jira("REN-4")`. A shared helper builds valid lease payloads
(`start 2026-01-01, rent "1200.00", due_day 1`).

**Unit: `tests/unit/test_ren4_schemas.py`**

| AC | Test |
|----|------|
| AC1 | `test_ac1_money_accepts_int_float_and_string_exactly` (`1200`, `1200.5`, `"1200.50"` → `Decimal`) |
| AC3 | `test_ac3_end_before_start_rejected` (field `end_date`); `test_ac3_end_equal_start_allowed` |
| AC3 | `test_ac3_rent_must_be_positive_with_two_decimals` (parametrised: `0`, `-1`, `"1200.555"`) |
| AC3 | `test_ac3_due_day_outside_range_rejected` (parametrised: `0`, `29`, `31`); `test_ac3_due_day_bounds_allowed` (`1`, `28`) |
| AC3 | `test_ac3_multiple_errors_reported_together` |
| AC1 | `test_ac1_lease_read_serialises_rent_as_two_decimal_string` |

**Unit: `tests/unit/test_ren4_services.py`**

| AC | Test |
|----|------|
| AC1 | `test_ac1_create_lease_is_active_with_exact_rent` |
| AC2 | `test_ac2_missing_tenant_property_or_both_raise_reference_error` (parametrised, checks the `missing` keys) |
| AC4 | `test_ac4_overlap_matrix` (parametrised over existing `[Mar 1, Jun 30]`): before / after / adjacent → allowed; overlapping start / end / inside / covering / same-day edge → `ConflictError` |
| AC4 | `test_ac4_open_ended_existing_lease_blocks_any_later_start`; `test_ac4_open_ended_new_lease_overlaps_later_existing` |
| AC4 | `test_ac4_other_property_never_conflicts` |
| AC4 | `test_ac4_ended_lease_still_blocks_its_covered_period` (D1); `test_ac4_ended_lease_frees_dates_after_its_end` |
| AC5 | `test_ac5_list_filters_by_tenant_property_and_both`; `test_ac5_unknown_filter_id_returns_empty` |
| AC6 | `test_ac6_end_lease_sets_status_and_end_date` |
| AC6 | `test_ac6_end_already_ended_raises_conflict`; `test_ac6_end_before_start_raises_rule_violation`; `test_ac6_end_later_than_existing_end_raises_rule_violation` (D2); `test_ac6_end_unknown_id_raises_not_found` |

**Unit: `tests/unit/test_ren4_rent.py`**

| AC | Test |
|----|------|
| AC6 | `test_ac6_no_due_dates_after_end_date` (end Mar 15, due day 1, through Dec → Feb 1, Mar 1 only) |
| AC6 | `test_ac6_end_date_on_due_day_is_included` |
| AC6 | `test_due_dates_first_due_on_or_after_start` (start Jan 15, due 1 → Feb 1; start Jan 1, due 1 → Jan 1; start Jan 10, due 20 → Jan 20) |
| AC6 | `test_due_dates_due_day_28_across_february_and_year_end` |
| AC6 | `test_due_dates_through_before_first_due_is_empty`; `test_due_dates_open_ended_stops_at_through` |

**Functional: `tests/functional/test_ren4_api.py`**

| AC | Test | Asserts |
|----|------|---------|
| AC1 | `test_ac1_post_lease_returns_201_active_with_id` | 201; `status: "active"`, `monthly_rent: "1200.00"`, dates ISO |
| AC1 | `test_ac1_lease_with_past_end_date_starts_active` (D4) | 201, `active` |
| AC2 | `test_ac2_unknown_tenant_or_property_returns_422_naming_it` (parametrised: tenant / property / both) | 422; `errors[].field` ⊇ expected |
| AC3 | `test_ac3_invalid_terms_return_400` (parametrised: end < start / rent 0 / rent −1 / due 0 / due 29) | 400; field named |
| AC3 | `test_ac3_validation_runs_before_reference_check` | bad `due_day` **and** unknown tenant → 400 (not 422) |
| AC4 | `test_ac4_overlapping_lease_returns_409`; `test_ac4_adjacent_lease_returns_201` | 409 / 201 |
| AC5 | `test_ac5_filter_by_tenant_id`; `test_ac5_filter_by_property_id`; `test_ac5_no_filter_lists_all` | only the matching ids |
| AC5 | `test_ac5_non_integer_filter_returns_400` | 400; field `tenantId` |
| AC5 | `test_ac5_get_lease_by_id`; `test_ac5_get_unknown_lease_returns_404` | 200 / 404 |
| AC6 | `test_ac6_end_lease_returns_200_ended` | 200; `status: "ended"`, `end_date` set; later GET agrees |
| AC6 | `test_ac6_end_twice_returns_409`; `test_ac6_end_unknown_returns_404`; `test_ac6_end_before_start_returns_400`; `test_ac6_end_later_than_existing_end_returns_400` | |
| AC6 | `test_ac6_end_missing_end_date_returns_400` | 400; field `end_date` |
| REN-3 | `test_delete_tenant_or_property_with_full_lease_still_409` | 409 |

Order: write the tests, update the REN-3 lease helpers, run everything, and confirm the REN-4 tests fail. Then implement.
The REN-2 and REN-3 suites must keep passing, and coverage must stay ≥ 90%.

## 7. Documentation

- `README.md`: add the `/leases` rows to the API table, and a note that leases need a fresh local DB
  ("delete `rentledger.db` after pulling REN-4").
