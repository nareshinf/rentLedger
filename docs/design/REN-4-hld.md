# REN-4 — Leases API: High-Level Design

- **Issue:** [REN-4](https://nareshmalhotra.atlassian.net/browse/REN-4) (parent epic REN-1)
- **Stage:** HLD (awaiting `hld-approved`)
- **Branch:** `REN-4-leases` (from `main` at `33d8a86`, REN-2 and REN-3 merged)
- **Builds on:** [REN-3 HLD](REN-3-hld.md) / [REN-3 LLD](REN-3-lld.md)

## 1. Goal

Let a landlord create leases that link a tenant to a property with rent terms, list and filter
them, and end them, so that rent due can be tracked (balances come in REN-5).

## 2. Scope

| AC | Outcome |
|----|---------|
| AC1 | `POST /leases` → 201 with `id` and status `active` |
| AC2 | Unknown tenant or property → **422** naming the missing reference |
| AC3 | End date before start, rent ≤ 0, or due day outside 1–28 → **400** with the errors |
| AC4 | New lease overlapping another lease on the same property → **409** |
| AC5 | `GET /leases?tenantId=…` / `?propertyId=…` → only the matching leases |
| AC6 | `POST /leases/{id}/end` with an end date → status `ended`, no rent accrues after that date |

**Also included** (needed by the conventions or by the ACs):
- `GET /leases/{id}` (200 / 404). CLAUDE.md requires 404 for an unknown path id, and AC6 needs it.
- The **rent due schedule** as a pure function (`due_dates`), with no endpoint. It's the only way to
  check "no rent accrues after that date" (AC6) now. REN-5 reuses it for balances.

**Out of scope:** payments and balances (REN-5), editing or deleting leases, proration,
automatically ending a lease when its end date passes.

## 3. Context

- REN-3 left a **minimal `leases` table** (`id`, `tenant_id`, `property_id`, `ON DELETE RESTRICT`).
  REN-4 adds the term columns. REN-3's delete protection (409) keeps working unchanged.
- The existing patterns to reuse are routers → services → models, `NotFoundError` (404),
  `ConflictError` (409), and the REN-2 validation handler (400 with `errors[].field`).
- CLAUDE.md rules that apply here:
  - Money is `Decimal` / `Numeric(12, 2)`, never float.
  - The due day is 1–28.
  - The status is `active` or `ended`.
  - Rent accrues once per due date from the lease start, and nothing accrues after the end date.
  - "Today" comes from the injectable clock.
- `search_kb` isn't available yet. Related designs: REN-2 and REN-3.

## 4. Design

### 4.1 Data model: `leases` (extended)

| Column | Type | Notes |
|--------|------|-------|
| `id`, `tenant_id`, `property_id` | as in REN-3 | |
| `start_date` | `Date` not null | |
| `end_date` | `Date` null | null = open-ended |
| `monthly_rent` | `Numeric(12, 2)` not null | `Decimal` in code |
| `due_day` | `Integer` not null | 1–28, also a DB `CHECK` |
| `status` | `String(10)` not null | `active` / `ended`, also a DB `CHECK` |
| `created_at` | `DateTime` | audit only, like REN-3 |

### 4.2 API

| Method & path | Success | Errors |
|---------------|---------|--------|
| `POST /leases` | 201 lease | 400 (AC3), 422 (AC2), 409 (AC4) |
| `GET /leases` (`tenantId`, `propertyId` optional, combined with AND) | 200 list, ordered by `id` | 400 (non-integer filter) |
| `GET /leases/{id}` | 200 lease | 404 |
| `POST /leases/{id}/end` body `{"end_date": "YYYY-MM-DD"}` | 200 lease (`status: ended`) | 400, 404, 409 |

Lease JSON: `{"id", "tenant_id", "property_id", "start_date", "end_date", "monthly_rent", "due_day", "status"}`.

- `monthly_rent` is accepted as a JSON number or string, and **returned as a string** (`"1200.00"`) so the
  exact value survives JSON. That's Pydantic's default for `Decimal`. It must be > 0, with at most 2 decimal places.
- A filter for a tenant or property that doesn't exist returns `200 []`, not 404. It's a search, not a lookup.

### 4.3 Order of checks on `POST /leases`

1. **400** for the body shape and terms (AC3), from schema validation: required fields, `end_date ≥ start_date`,
   `monthly_rent > 0`, `due_day` 1–28. All failing fields are reported together.
2. **422** for missing references (AC2). A new `ReferenceNotFoundError` is mapped to 422 with
   `{"detail": "...", "errors": [{"field": "tenant_id", "message": "Tenant 99 does not exist"}]}`.
   Both references are checked and every missing one is reported.
3. **409** for an overlap (AC4) through `ConflictError`.

### 4.4 Overlap rule (AC4)

Two leases on the same property overlap when `a.start ≤ b.end` and `b.start ≤ a.end`, both
**inclusive**, with a null end treated as open-ended. So a lease ending 2026-06-30 and one starting
2026-07-01 don't overlap, but one starting 2026-06-30 does.

Which existing leases count is **decision D1** (§6).

### 4.5 Ending a lease (AC6)

`POST /leases/{id}/end` sets `end_date` to the given date and `status` to `ended` in one transaction.
- `end_date < start_date` → 400.
- Lease already `ended` → 409.
- Whether the new end can be *later* than an existing `end_date` is **decision D2**.
- The end date can be in the future (for example a notice period). The status becomes `ended` straight away,
  and rent still accrues on due dates up to and including the end date.

### 4.6 Rent due schedule (`app/services/rent.py`)

`due_dates(lease, through: date) -> list[date]` returns every date on which rent is due, using the
CLAUDE.md rule:
- The first due date is the first `due_day` **on or after** `start_date`. For example, start Jan 15 with due day 1
  gives a first charge on Feb 1. There's no proration, which follows the CLAUDE.md wording "once per due date from lease start".
- After that it's monthly on `due_day`, up to `min(through, end_date)` inclusive.
- `through` is passed in. The function never reads the clock itself, so REN-5 supplies "today" or `asOf`.

AC6 is then tested by checking that `due_dates` returns nothing after the end date.

## 5. Schema change

`create_all` doesn't alter existing tables, so **a local `rentledger.db` from REN-3 has to be deleted**.
The README will say so. CI and the tests always start from an empty database. This is the
no-migrations risk recorded in the REN-3 HLD.

## 6. Decisions needed

| # | Question | Recommendation |
|---|----------|----------------|
| **D1** | Does the overlap check (AC4) consider only `active` leases, as the AC says, or **all** leases? | **All leases, by their date ranges.** An ended lease's range stops at its end date, so ending a lease early still frees the property after that date. Ignoring ended leases completely would let two leases charge rent for the same period on one property. |
| **D2** | Can `/end` move an existing end date *later*? | **No: only the same date or earlier** (otherwise 400). Extending a lease would need its own overlap re-check, so it's better as a separate story. |
| **D3** | Naming: AC5 uses camelCase query params (`tenantId`), but REN-3 JSON is snake_case. | **Query params camelCase, exactly as in AC5 (and `asOf` in REN-5); JSON bodies stay snake_case**, consistent with REN-3. The alternative is to switch everything to camelCase, which would change the REN-3 API. |
| **D4** | A lease created with an end date already in the past still starts `active` (AC1). OK? | **Yes, follow AC1.** Status only changes through `/end`. |

## 7. Test strategy

Every test is marked `@pytest.mark.jira("REN-4")` and named `test_acN_...`.

| AC | Unit | Functional |
|----|------|-----------|
| AC1 | create lease sets `active` and keeps the `Decimal` rent exactly | POST → 201, body has `id`, `status: active`, `monthly_rent: "1200.00"` |
| AC2 | missing tenant/property raises `ReferenceNotFoundError` naming the field(s) | POST with unknown tenant / property / both → 422, `errors[].field` |
| AC3 | schema rejects end < start, rent 0 / negative / 3 decimal places, due day 0 / 29 | POST → 400 naming `end_date` / `monthly_rent` / `due_day` |
| AC4 | overlap matrix: before, after, touching, inclusive edge, open-ended, other property, ended lease (per D1) | POST overlapping → 409; adjacent → 201 |
| AC5 | filter by tenant, by property, both, unknown id → empty | GET with each filter → only the matching ids; non-integer → 400 |
| AC6 | `due_dates` stops at the end date; first-due-date rule; due day 28 across February; `/end` rules (D2, already ended) | POST `/end` → 200 `ended`; again → 409; unknown id → 404; end < start → 400 |
| REN-3 regression | — | deleting a tenant or property with a full lease still → 409 |

## 8. Risks

- **Local DB has to be recreated** (§5).
- **D1–D4** change behaviour and tests, so please confirm them before the LLD.
