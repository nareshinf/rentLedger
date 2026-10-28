# REN-5 — Payments and balance: High-Level Design

- **Issue:** [REN-5](https://nareshmalhotra.atlassian.net/browse/REN-5) (parent epic REN-1)
- **Stage:** HLD (awaiting `hld-approved`)
- **Branch:** `REN-5-payments-balance`, stacked on `REN-4-leases` (PR #3 not merged yet)
- **Builds on:** [REN-4 HLD](REN-4-hld.md) / [REN-4 LLD](REN-4-lld.md), especially `due_dates()`

## 1. Goal

Record rent payments against a lease and show the lease's balance (charged, paid, owed or
in credit), optionally as of a given date, with exact money arithmetic.

## 2. Scope

| AC | Outcome |
|----|---------|
| AC1 | `POST /leases/{id}/payments` (amount > 0, payment date, optional method/note) → 201 |
| AC2 | Amount ≤ 0 or a missing date → 400 |
| AC3 | Unknown lease id → 404 |
| AC4 | `GET /leases/{id}/payments` → payments in date order |
| AC5 | `GET /leases/{id}/balance` → `charged = N × R`, `paid = P`, `balance = charged − paid` |
| AC6 | Overpayment → negative balance (credit) |
| AC7 | `?asOf=YYYY-MM-DD` → only charges due and payments made on or before that date |
| AC8 | Amounts with cents give no floating-point error |

**Out of scope:** editing or deleting payments, receipts and notifications, late fees, proration,
allocating payments to particular months, and portfolio-wide or per-tenant balance reports.

## 3. Context

- REN-4 gives the `Lease` model (`monthly_rent` `Numeric(12,2)`, `due_day`, `start_date`, `end_date`)
  and the pure `due_dates(start, end, due_day, through)`. That function already implements the CLAUDE.md
  accrual rule: "once per due date from lease start; nothing after the end date".
- REN-2 gives the injectable `Clock` / `get_clock()` dependency. CLAUDE.md requires it for "today".
- The existing patterns reused here: routers → services → models, `NotFoundError` (404), the REN-2
  validation handler (400 with `errors[].field`), `Money` (Decimal > 0, 2 decimal places), money returned as strings,
  camelCase query params and snake_case bodies (REN-4 D3).

## 4. Design

### 4.1 Data model: `payments` (new)

| Column | Type | Notes |
|--------|------|-------|
| `id` | int PK | |
| `lease_id` | FK → `leases.id`, `ON DELETE RESTRICT`, indexed | |
| `amount` | `Numeric(12, 2)` not null | DB `CHECK amount > 0` |
| `paid_on` | `Date` not null | |
| `method` | `String(50)` null | free text, for example "bank transfer" (see P3) |
| `note` | `String(500)` null | |
| `created_at` | `DateTime` | audit only |

This is a new table. `create_all` adds it to an existing local DB without changing anything else, so no
DB reset is needed for REN-5 beyond the one REN-4 already requires.

### 4.2 API

| Method & path | Success | Errors |
|---------------|---------|--------|
| `POST /leases/{id}/payments` | 201 payment | 400 (AC2), 404 (AC3) |
| `GET /leases/{id}/payments` | 200 list ordered by `paid_on`, then `id` | 404 |
| `GET /leases/{id}/balance?asOf=YYYY-MM-DD` | 200 balance | 400 (bad date), 404 |

Payment JSON: `{"id", "lease_id", "amount": "1234.56", "paid_on": "YYYY-MM-DD", "method", "note"}`.

Balance JSON:
```json
{"lease_id": 7, "as_of": "2026-04-30", "monthly_rent": "1200.00",
 "charges_due": 4, "charged": "4800.00", "paid": "4500.00", "balance": "300.00"}
```
`charges_due` is N from AC5. It's included so a reader can check `charged = N × R` without
working out the schedule.

### 4.3 Balance calculation (`app/services/balance.py`)

```
as_of    = asOf query param, or Clock.today() when omitted
N        = len(due_dates(lease.start_date, lease.end_date, lease.due_day, through=as_of))
charged  = N × lease.monthly_rent
paid     = Σ payment.amount for payments with paid_on ≤ as_of
balance  = charged − paid        (negative = credit, AC6)
```
- **Exactness (AC8):** all arithmetic is `Decimal`. `paid` is summed **in Python over `Decimal` values**,
  not with SQL `SUM()`, because SQLite's `SUM` over a REAL-stored column returns a float. The results are
  quantised to 2 decimal places and returned as strings.
- `asOf` before the lease start gives `charged = 0`. Any earlier payments still count, which shows as credit.
- `asOf` in the future is allowed. It projects the charges due by that date.
- An ended lease stops charging at its `end_date` through `due_dates`, which REN-4 AC6 already tests.

### 4.4 Recording a payment

The schema validates `amount` as `Money` (> 0, at most 2 decimal places), `paid_on` as a required date, and `method` /
`note` as optional, trimmed, non-empty strings. The service checks the lease exists (404). Per P1, ended leases accept payments. Per P2, a
`paid_on` later than `Clock.today()` → 400 on `paid_on`.

## 5. Decisions (recommendations accepted in review)

| # | Question | **Decision** |
|---|----------|----------------|
| **P1** | AC1 says "an active lease". Can payments be recorded on an **ended** lease? | **Yes.** Tenants often pay arrears after moving out, and the balance should still go to zero. Payments are only refused for unknown leases (404). |
| **P2** | Can a payment be dated **in the future**? | **No → 400** (`paid_on` after today from the `Clock`). A future-dated payment is almost always a typo, and it would silently skew today's balance. |
| **P3** | `method`: free text or a fixed list? | **Free text** (optional, ≤ 50 characters). The AC only says "optional method". A fixed list can be added later without breaking anyone. |
| **P4** | Field name for the payment date: `paid_on` or `payment_date`? | **`paid_on`**, which is short and reads well next to `as_of`. Bodies stay snake_case per REN-4 D3. |

## 6. Test strategy

Every test is marked `@pytest.mark.jira("REN-5")` and named `test_acN_...`. Time is frozen by overriding
`get_clock` with a `FixedClock` in functional tests and passing `through`/`as_of` explicitly in unit tests.

| AC | Unit | Functional |
|----|------|-----------|
| AC1 | create payment with and without method/note | POST → 201, body has `id`, `amount` string, `paid_on`; ended lease also accepted (P1) |
| AC2 | schema rejects amount 0, negative, 3 decimal places, missing `paid_on`; future `paid_on` (P2) | POST → 400 naming `amount` / `paid_on` |
| AC3 | service raises `NotFoundError` | POST, GET payments, GET balance on unknown lease → 404 |
| AC4 | list ordered by date then id, whatever the insert order | GET → dates ascending |
| AC5 | N from schedule × R; `charges_due` matches | GET balance with FixedClock → exact `charged` / `paid` / `balance` |
| AC6 | overpaid → negative | GET → `balance` starts with `-` |
| AC7 | `as_of` boundaries: due date on `as_of` counted, payment on `as_of` counted, the day after not; `as_of` before start → 0 charged | `?asOf=` mid-history; `?asOf=bad` → 400 |
| AC8 | 1234.56 × 7 and many cent payments sum exactly; payments read back from SQLite sum exactly | e.g. three payments of `0.10`, `0.20`, `0.30` → `paid: "0.60"` |

## 7. Risks

- **The balance depends on `due_dates`.** Any change to the accrual rule changes every balance. REN-4's schedule tests guard it.
- **SQLite float storage:** kept exact by quantising on read (verified in REN-4) and by not using SQL `SUM`.
- **Stacked branch:** REN-5's PR targets `main` after PR #3 merges, or `REN-4-leases` until then.
