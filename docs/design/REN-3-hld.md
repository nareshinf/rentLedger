# REN-3 — Tenants and properties API: High-Level Design

- **Issue:** [REN-3](https://nareshmalhotra.atlassian.net/browse/REN-3) (parent epic REN-1)
- **Stage:** HLD (awaiting `hld-approved`)
- **Branch:** `REN-3-tenants-properties`, stacked on `REN-2-skeleton` (PR #1 not merged yet)
- **Builds on:** [REN-2 HLD](REN-2-hld.md) / [REN-2 LLD](REN-2-lld.md)

## 1. Goal

Let a landlord create, read, list, update and delete **tenants** and **properties**, so that
leases (REN-4) and payments (REN-5) can be attached to them.

## 2. Scope

| AC | Outcome |
|----|---------|
| AC1 | `POST /properties` (name, address) → 201 with `id` |
| AC2 | `POST /tenants` (full name, email, optional phone) → 201 with `id` |
| AC3 | `GET /tenants`, `GET /tenants/{id}`, `GET /properties`, `GET /properties/{id}` → 200 |
| AC4 | `PATCH` tenant/property with valid fields → 200, later reads show the change |
| AC5 | Missing required field or invalid email → 400 naming the field(s) |
| AC6 | Unknown id on GET / PATCH / DELETE → 404 |
| AC7 | DELETE of a tenant/property referenced by a lease → 409, record kept |

**Out of scope:** the leases API and lease rules (REN-4), payments and balances (REN-5),
pagination, filtering and search, authentication.

## 3. Context

- REN-2 provides `create_app()`, `app/db.py` (`Base`, `get_session`, per-app session factory),
  and the `RequestValidationError` → 400 handler (`{"detail", "errors": [{"field", "message"}]}`).
  AC5 reuses that handler, so no new error-handling code is needed for it.
- `search_kb` isn't available (the KB isn't built yet). The only related designs are REN-2's.

## 4. Design

### 4.1 Layers (sets the pattern REN-4/REN-5 will follow)

```
routers/tenants.py, routers/properties.py   HTTP only: parse, call service, map errors to status
        │
services/tenants.py, services/properties.py plain functions taking a Session; business rules
        │                                    raise domain errors (NotFound, Conflict)
models.py  (SQLAlchemy)  ◀── schemas.py (Pydantic: Create / Update / Read per resource)
```

- **Domain errors:** `app/services/errors.py` defines `NotFoundError` and `ConflictError`.
  Handlers registered in `create_app()` map them to **404** and **409**, with
  `{"detail": "<message>"}`. Routers stay thin, and REN-4/REN-5 reuse the same errors.
- **Transactions:** each service call commits on success. A failed request rolls back.

### 4.2 Data model

| Table | Columns |
|-------|---------|
| `properties` | `id` int PK, `name` str(200) not null, `address` str(500) not null, `created_at` |
| `tenants` | `id` int PK, `full_name` str(200) not null, `email` str(320) not null, `phone` str(50) null, `created_at` |

- Tables are created with `Base.metadata.create_all(engine)` at app start-up. There are no migrations
  in the stack yet (see §7).
- SQLite foreign-key enforcement is switched on (`PRAGMA foreign_keys=ON` on connect) so the
  lease foreign keys added in REN-4 are actually enforced.

### 4.3 API

| Method & path | Success | Errors |
|---------------|---------|--------|
| `POST /properties` | 201 property | 400 |
| `GET /properties` | 200 list (ordered by `id`) | — |
| `GET /properties/{id}` | 200 property | 404 |
| `PATCH /properties/{id}` | 200 property | 400, 404 |
| `DELETE /properties/{id}` | **204** no body | 404, 409 |
| same five for `/tenants` | | |

- **Field names:** JSON uses snake_case (`full_name`) to match the AC wording and Pydantic defaults.
- **PATCH** is a partial update: only fields that are sent change. An explicit `null` for a required
  field, or an empty string, → 400. An empty body → 200 with nothing changed.
- **Validation:** non-empty, trimmed strings with max lengths matching the columns. `email` is checked with
  Pydantic `EmailStr` and stored lower-cased. `phone` is optional, free text, max 50 characters.
- **Path ids** that aren't integers → 400 (through the REN-2 handler). Integer ids that don't exist → 404.

### 4.4 Delete protection (AC7): needs a decision

AC7 depends on **leases, which REN-4 introduces**. Options:

1. **(Recommended)** REN-3 adds a **minimal `leases` table**: `id`, `tenant_id` FK, `property_id` FK, both
   `ON DELETE RESTRICT`, and no API. The tenant and property delete services check for referencing
   leases and raise `ConflictError` → 409. The FK is a second safety net. REN-4 adds the
   remaining lease columns, rules and endpoints. AC7 is fully tested in REN-3 by inserting a lease
   row directly in the test.
2. REN-3 ships DELETE without the 409 rule, and AC7 is deferred to REN-4. This leaves AC7 unmet for REN-3.

## 5. New library

- **`email-validator`** (through `pydantic[email]`), needed by `EmailStr` for AC5's "invalid email".
  It's the validator Pydantic officially supports. A hand-written regex would be weaker and
  something extra to maintain.

## 6. Test strategy

Every test is marked `@pytest.mark.jira("REN-3")` and named `test_acN_...`.

| AC | Unit (services, in-memory SQLite) | Functional (TestClient, temp SQLite file) |
|----|-----------------------------------|-------------------------------------------|
| AC1 | create property returns the row with an id | POST → 201, body has `id`, `name`, `address` |
| AC2 | create tenant with and without phone; email lower-cased | POST → 201 with/without phone |
| AC3 | get / list return the stored rows | GET list → 200 with all; GET by id → 200 |
| AC4 | partial update changes only the fields sent | PATCH → 200; later GET reflects it |
| AC5 | schema rejects missing/blank/too-long fields and a bad email | POST/PATCH bad payload → 400, `errors[].field` names it (`email`, `name`, …) |
| AC6 | get/update/delete of unknown id raises `NotFoundError` | GET/PATCH/DELETE unknown id → 404 (both resources) |
| AC7 | delete with a referencing lease raises `ConflictError` | DELETE referenced tenant/property → 409, and a later GET still → 200; unreferenced → 204 then 404 |

## 7. Risks and open points

- **AC7 approach:** please approve option 1 or 2 in §4.4.
- **Email uniqueness:** the ACs don't ask for it, so it isn't enforced. Two tenants can share an email. Please say if you want 409 on a duplicate email.
- **No migrations:** `create_all` doesn't change tables that already exist. REN-4 adding lease columns means
  deleting any local `rentledger.db`. If you want Alembic, it should be its own issue.
- **Stacked branch:** REN-3's PR will target `main` after PR #1 merges (or `REN-2-skeleton` until then).
