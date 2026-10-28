# REN-2 — Project skeleton and CI: Low-Level Design

- **Issue:** [REN-2](https://nareshmalhotra.atlassian.net/browse/REN-2)
- **HLD:** [REN-2-hld.md](REN-2-hld.md) (`hld-approved`)
- **Stage:** LLD (awaiting `lld-approved`)

## 1. Files

| Path | Purpose |
|------|---------|
| `pyproject.toml` | Package metadata, deps, `[dev]` extra, ruff, pytest, coverage config |
| `.gitignore` | `.venv/`, `__pycache__/`, `.coverage`, `htmlcov/`, `*.db`, `.pytest_cache/`, `.ruff_cache/` |
| `README.md` | Install, run, test, lint, and CI description (AC5) |
| `.github/workflows/ci.yml` | CI pipeline (AC3, AC4) |
| `app/__init__.py` | Package marker |
| `app/main.py` | `create_app()` factory and module-level `app` |
| `app/db.py` | DB URL resolution, engine and session factories, `Base`, `get_session` |
| `app/errors.py` | `RequestValidationError` → 400 handler (split from `main.py` to keep it small) |
| `app/models.py` | Imports `Base`. No tables yet |
| `app/schemas.py` | `HealthResponse` |
| `app/routers/__init__.py`, `app/routers/health.py` | `GET /health` |
| `app/services/__init__.py`, `app/services/clock.py` | `Clock` protocol, `SystemClock`, `FixedClock`, `get_clock` |
| `tests/conftest.py` | Markers, `--jira` option, `app` / `client` fixtures |
| `tests/unit/test_ren2_*.py`, `tests/functional/test_ren2_*.py` | Tests (§4) |

## 2. Module detail

### `pyproject.toml`
- `[project]`: `name = "rentledger"`, `requires-python = ">=3.12"`. Deps: `fastapi>=0.115`,
  `uvicorn[standard]>=0.30`, `sqlalchemy>=2.0`, `pydantic>=2.7`.
- `[project.optional-dependencies] dev`: `pytest>=8`, `pytest-cov>=5`, `httpx>=0.27`, `ruff>=0.6`,
  `pyyaml>=6` (already pulled in by `uvicorn[standard]`; pinned here because the tests import it).
- `[tool.setuptools.packages.find] include = ["app*"]`.
- `[tool.pytest.ini_options]`: `testpaths = ["tests"]`,
  `addopts = "--strict-markers --cov=app --cov-branch --cov-report=term-missing --cov-fail-under=90"`.
  The markers `jira(key)` and `self_run` are registered in `conftest.py`.
- `[tool.ruff]`: `line-length = 100`, `target-version = "py312"`; `lint.select = ["E","F","I","B","UP"]`.

### `app/db.py`
```python
DEFAULT_DATABASE_URL = "sqlite:///./rentledger.db"
DATABASE_URL_ENV = "RENTLEDGER_DATABASE_URL"

def get_database_url(environ: Mapping[str, str] = os.environ) -> str  # env value or default
def make_engine(url: str) -> Engine            # sqlite → connect_args={"check_same_thread": False}
def make_session_factory(engine) -> sessionmaker[Session]
class Base(DeclarativeBase): ...
def get_session(request: Request) -> Iterator[Session]
    # yields request.app.state.session_factory(); closes in finally
```

### `app/errors.py`
```python
def format_validation_errors(errors: Sequence[dict]) -> list[dict[str, str]]
    # loc ("body", "name") → field "name"; drops a leading "body"/"query"/"path"/"header"
    # → [{"field": "name", "message": "Field required"}]
async def validation_exception_handler(request, exc: RequestValidationError) -> JSONResponse
    # 400 {"detail": "Validation failed", "errors": format_validation_errors(exc.errors())}
```

### `app/main.py`
```python
def create_app(database_url: str | None = None) -> FastAPI:
    # url = database_url or get_database_url()
    # app.state.engine / app.state.session_factory
    # add_exception_handler(RequestValidationError, validation_exception_handler)
    # include_router(health.router)
app = create_app()
```

### `app/routers/health.py`
`GET /health`, `response_model=HealthResponse` → `{"status": "ok"}`. It doesn't touch the DB.

### `app/services/clock.py`
`Clock` is a `Protocol` with `today() -> date`. `SystemClock` returns `date.today()`, which is the only
call to it in the code base. `FixedClock(day)` is for tests. `get_clock() -> Clock` returns a `SystemClock` and
is the FastAPI dependency that tests override.

## 3. CI workflow (`.github/workflows/ci.yml`)

```yaml
name: CI
on:
  pull_request: { branches: [main] }
  push: { branches: [main] }
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5   # python-version "3.12", cache pip
      - name: Install dependencies   run: pip install -e ".[dev]"
      - name: Lint                   run: ruff check .
      - name: Format check           run: ruff format --check .
      - name: Tests                  run: pytest
```
The workflow has no `continue-on-error` and no `|| true`, so any non-zero step fails the job (AC4).

## 4. Test plan

Every test is marked `@pytest.mark.jira("REN-2")`. `--jira REN-2` keeps only the tests with that marker.

**conftest.py**
- `pytest_addoption`: `--jira KEY`.
- `pytest_configure`: registers `jira(key)` and `self_run`.
- `pytest_collection_modifyitems`: when `--jira` is given, deselects items whose `jira` marker
  doesn't match.
- Fixtures: `app(tmp_path)` → `create_app(f"sqlite:///{tmp_path}/test.db")`, and `client(app)` → `TestClient`.

| AC | Test | Kind | Asserts |
|----|------|------|---------|
| AC1 | `test_ac1_health_returns_ok` | functional | `GET /health` → 200, body `{"status":"ok"}` |
| AC1 | `test_ac1_create_app_registers_health_route` | unit | `/health` (GET) is in `app.routes` |
| AC1 | `test_ac1_database_url_defaults_and_env_override` | unit | `get_database_url({})` → default; env value wins |
| AC1 | `test_ac1_sqlite_engine_allows_cross_thread` | unit | the engine connects and `SELECT 1` works |
| AC1 | `test_ac1_service_starts_with_uvicorn` | functional | subprocess `python -m uvicorn app.main:app --port <free>` → `/health` 200 within 15 s |
| AC1 | `test_ac1_session_dependency_yields_working_session` | functional | a test-only route that uses `get_session` runs `SELECT 1` → 200 |
| AC2 | `test_ac2_test_suite_exits_zero` | functional, `self_run` | subprocess `pytest -m "not self_run" --no-cov -q -p no:cacheprovider` → exit 0 |
| AC3 | `test_ac3_ci_triggers_on_pull_request_to_main` | unit | the `pull_request.branches` list in `ci.yml` contains `main` |
| AC3 | `test_ac3_ci_installs_lints_and_tests` | unit | the step `run`s contain `pip install -e ".[dev]"`, `ruff check`, `ruff format --check`, `pytest`, in that order |
| AC3 | `test_ac3_ci_uses_python_312` | unit | setup-python `python-version` is `"3.12"` |
| AC4 | `test_ac4_ci_failures_are_not_masked` | unit | no `continue-on-error`, and no `|| true` / `; exit 0` in any step |
| AC5 | `test_ac5_readme_documents_install_run_test` | unit | README has the install command, `uvicorn app.main:app` and `pytest` |
| x-cut | `test_ac1_validation_error_returns_400_naming_field` | functional | a test route with a Pydantic body, sent `{}` → 400, `errors[0].field == "name"` |
| x-cut | `test_format_validation_errors_strips_location_prefix` | unit | `("body","name")` → `"name"`; `("query","limit")` → `"limit"`; a nested loc is joined with `.` |
| x-cut | `test_fixed_clock_returns_given_day`, `test_system_clock_returns_today` | unit | clock behaviour |

Notes:
- PyYAML parses the YAML key `on:` as the boolean `True`, so the tests read `wf.get("on", wf.get(True))`.
- The AC2 self-run uses `--no-cov` so that the inner run doesn't overwrite the outer `.coverage`, and
  `-m "not self_run"` so that it doesn't recurse.
- The uvicorn smoke test points `RENTLEDGER_DATABASE_URL` at `tmp_path`, picks a free port, and
  always terminates the process in `finally`.
- **Write tests first, then confirm they fail** (missing `app` package / files) before implementing.

## 5. Implementation order
1. `pyproject.toml`, `.gitignore`; Python 3.12 venv via `uv venv --python 3.12`; `uv pip install -e ".[dev]"`.
2. `tests/` per §4. Run `pytest` and record that it fails.
3. `app/` modules, `ci.yml`, `README.md`.
4. `ruff check . && ruff format --check .` and `pytest` (coverage ≥ 90 %).
5. Commit `REN-2: ...`, comment the evidence table on REN-2, and move REN-2 to **In Review**.
