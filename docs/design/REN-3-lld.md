# REN-3 — Tenants and properties API: Low-Level Design

- **Issue:** [REN-3](https://nareshmalhotra.atlassian.net/browse/REN-3)
- **HLD:** [REN-3-hld.md](REN-3-hld.md) (`hld-approved`; AC7 option 1, no email uniqueness)
- **Stage:** LLD (awaiting `lld-approved`)

## 1. Files

| Path | Change |
|------|--------|
| `pyproject.toml` | `pydantic>=2.7` → `pydantic[email]>=2.7` (adds `email-validator`) |
| `app/db.py` | SQLite `PRAGMA foreign_keys=ON` on every connection; `create_tables(engine)` |
| `app/models.py` | `Property`, `Tenant`, minimal `Lease` |
| `app/schemas.py` | `PropertyCreate/Update/Read`, `TenantCreate/Update/Read` (alongside `HealthResponse`) |
| `app/services/errors.py` | **new**: `NotFoundError`, `ConflictError` |
| `app/services/properties.py`, `app/services/tenants.py` | **new**: CRUD services |
| `app/routers/properties.py`, `app/routers/tenants.py` | **new**: endpoints |
| `app/errors.py` | add `not_found_handler` (404) and `conflict_handler` (409) |
| `app/main.py` | lifespan creates tables; register the new handlers and routers |
| `tests/conftest.py` | add the `db_session` fixture (in-memory SQLite, `StaticPool`) |
| `tests/unit/test_ren3_*.py`, `tests/functional/test_ren3_*.py` | tests (§5) |
| `README.md` | short "API" section listing the new endpoints |

## 2. Data layer

### `app/db.py` additions
```python
def make_engine(url: str) -> Engine:
    # unchanged connect_args; for sqlite also:
    #   event.listen(engine, "connect", lambda conn, _: conn.execute("PRAGMA foreign_keys=ON"))
def create_tables(engine: Engine) -> None:
    import app.models  # noqa: F401  registers the mappers
    Base.metadata.create_all(engine)
```

### `app/models.py`
```python
class Property(Base):    __tablename__ = "properties"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    address: Mapped[str] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

class Tenant(Base):      __tablename__ = "tenants"
    id, full_name String(200), email String(320), phone String(50) | None, created_at

class Lease(Base):       __tablename__ = "leases"   # minimal; REN-4 adds terms, dates, status
    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id", ondelete="RESTRICT"), index=True)
    property_id: Mapped[int] = mapped_column(ForeignKey("properties.id", ondelete="RESTRICT"), index=True)
```
`created_at` is for auditing only and isn't exposed in the API.

### `app/main.py`
A `lifespan` context manager calls `create_tables(app.state.engine)` on start-up. Doing this in
start-up rather than in `create_app()` means importing `app.main` (which builds the module-level `app`)
never creates `./rentledger.db` as a side effect. `TestClient` used as a context manager runs the
lifespan.

## 3. Schemas (`app/schemas.py`)

```python
Name    = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
Address = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]
Phone   = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=50)]

class PropertyCreate(BaseModel): name: Name; address: Address
class PropertyUpdate(BaseModel): name: Name | None = None; address: Address | None = None
    # field_validator("name", "address", mode="before"): an explicit None → ValueError("may not be null")
class PropertyRead(BaseModel):   model_config = ConfigDict(from_attributes=True); id: int; name: str; address: str

class TenantCreate(BaseModel):   full_name: Name; email: EmailStr; phone: Phone | None = None
    # field_validator("email") → .lower()
class TenantUpdate(BaseModel):   full_name: Name | None = None; email: EmailStr | None = None
                                 phone: Phone | None = None
    # explicit None is rejected for full_name and email; allowed for phone (clears it)
class TenantRead(BaseModel):     from_attributes; id; full_name; email; phone: str | None
```
`extra` fields are ignored (the Pydantic default). Validation errors are formatted by the REN-2 handler:
for example, a missing `email` → `400 {"errors": [{"field": "email", ...}]}`.

## 4. Services and routers

### `app/services/errors.py`
```python
class NotFoundError(Exception):  __init__(self, resource: str, id: int) → message "<Resource> <id> not found"
class ConflictError(Exception):  __init__(self, message: str)
```

### `app/services/properties.py` (`tenants.py` is the same shape)
```python
def create_property(session, data: PropertyCreate) -> Property       # add, commit, refresh
def list_properties(session) -> list[Property]                        # ORDER BY id
def get_property(session, property_id: int) -> Property               # NotFoundError if missing
def update_property(session, property_id, data: PropertyUpdate) -> Property
    # get_property(); setattr for data.model_dump(exclude_unset=True); commit; refresh
def delete_property(session, property_id) -> None
    # get_property(); if session.scalar(select(exists().where(Lease.property_id == id))):
    #     raise ConflictError("Property <id> is referenced by a lease")
    # session.delete(); commit
```

### `app/errors.py` additions
`not_found_handler` → `404 {"detail": str(exc)}` and `conflict_handler` → `409 {"detail": str(exc)}`,
both registered in `create_app()`.

### Routers
`APIRouter(prefix="/properties", tags=["properties"])`, and the same for `/tenants`. The session comes from
`Annotated[Session, Depends(get_session)]`.

| Endpoint | Signature | Status / model |
|----------|-----------|----------------|
| `POST /properties` | `body: PropertyCreate` | 201, `PropertyRead` |
| `GET /properties` | — | 200, `list[PropertyRead]` |
| `GET /properties/{property_id}` | `property_id: int` | 200, `PropertyRead` |
| `PATCH /properties/{property_id}` | `body: PropertyUpdate` | 200, `PropertyRead` |
| `DELETE /properties/{property_id}` | — | 204, empty body (`Response`) |
| `/tenants…` | `tenant_id`, `TenantCreate/Update` | same codes, `TenantRead` |

A non-integer path id → 400 with `field: "property_id"` (REN-2 handler).

## 5. Test plan

All tests are marked `@pytest.mark.jira("REN-3")`. **Unit** tests use `db_session` (in-memory SQLite,
tables created, FK pragma on). **Functional** tests use the existing `client` fixture (temp SQLite file,
lifespan runs). Leases for AC7 are inserted directly via `Lease(tenant_id=…, property_id=…)` in a session
from `app.state.session_factory`.

**Unit: `tests/unit/test_ren3_services.py`**

| AC | Test |
|----|------|
| AC1 | `test_ac1_create_property_assigns_id` |
| AC2 | `test_ac2_create_tenant_with_and_without_phone`, `test_ac2_tenant_email_is_lowercased` |
| AC3 | `test_ac3_list_returns_rows_in_id_order`, `test_ac3_get_returns_row` (both resources) |
| AC4 | `test_ac4_update_changes_only_sent_fields`, `test_ac4_tenant_phone_can_be_cleared` |
| AC6 | `test_ac6_get_update_delete_unknown_id_raise_not_found` (parametrised over both resources × 3 ops) |
| AC7 | `test_ac7_delete_referenced_property_raises_conflict_and_keeps_row`, `..._tenant_...`, `test_ac7_fk_restrict_blocks_raw_delete` (safety net: IntegrityError) |
| AC7 | `test_ac7_delete_unreferenced_removes_row` |

**Unit: `tests/unit/test_ren3_schemas.py`**

| AC | Test |
|----|------|
| AC5 | `test_ac5_property_create_requires_name_and_address` |
| AC5 | `test_ac5_blank_or_too_long_strings_rejected` (parametrised) |
| AC5 | `test_ac5_invalid_email_rejected` (parametrised: `"no-at"`, `"a@"`, `"@b.com"`) |
| AC5 | `test_ac5_update_rejects_explicit_null_for_required_fields` |

**Functional: `tests/functional/test_ren3_api.py`**

| AC | Test | Asserts |
|----|------|---------|
| AC1 | `test_ac1_post_property_returns_201_with_id` | 201; body `{id, name, address}` |
| AC2 | `test_ac2_post_tenant_returns_201_with_id` | 201; `phone` null when omitted, set when sent |
| AC3 | `test_ac3_list_and_get_tenants`, `test_ac3_list_and_get_properties` | 200; list contains created; get matches |
| AC4 | `test_ac4_patch_property_then_get_reflects_change`, `test_ac4_patch_tenant_then_get_reflects_change` | 200 then GET shows the new value |
| AC5 | `test_ac5_post_tenant_missing_full_name_returns_400` | 400; `errors[].field` contains `full_name` |
| AC5 | `test_ac5_post_tenant_invalid_email_returns_400` | 400; field `email` |
| AC5 | `test_ac5_post_property_missing_fields_returns_400_naming_both` | fields `name`, `address` |
| AC5 | `test_ac5_patch_with_invalid_email_returns_400` | 400; field `email` |
| AC6 | `test_ac6_unknown_id_returns_404` (parametrised: GET/PATCH/DELETE × tenants/properties) | 404 |
| AC6 | `test_ac6_non_integer_id_returns_400` | 400 |
| AC7 | `test_ac7_delete_referenced_property_returns_409_and_keeps_record` | 409; later GET → 200 |
| AC7 | `test_ac7_delete_referenced_tenant_returns_409_and_keeps_record` | 409; later GET → 200 |
| AC7 | `test_ac7_delete_unreferenced_returns_204_then_404` | 204 empty; later GET → 404 |

Order: write the tests, run them, and confirm they fail (missing modules/routes), then implement.
The REN-2 suite must keep passing, and overall coverage must stay ≥ 90%.

## 6. Documentation

- `README.md`: add an "API" section listing the tenant and property endpoints and status codes.
- `docs/` overview/glossary don't exist yet, so there's nothing else to update.
