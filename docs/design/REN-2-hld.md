# REN-2 — Project skeleton and CI: High-Level Design

- **Issue:** [REN-2](https://nareshmalhotra.atlassian.net/browse/REN-2) (parent epic REN-1, "RentLedger baseline")
- **Stage:** HLD (awaiting `hld-approved`)
- **Branch:** `REN-2-skeleton`

## 1. Goal

Give RentLedger a runnable FastAPI service and an automated CI pipeline, so every later
story (REN-3 to REN-5) is built, linted and tested the same way locally and on pull requests.

## 2. Scope

**In scope**

| AC | Outcome |
|----|---------|
| AC1 | `uvicorn app.main:app` starts the service; `GET /health` → `200 {"status": "ok"}` |
| AC2 | `pytest` runs the suite and exits 0 |
| AC3 | GitHub Actions on PRs to `main`: install deps, run lint and tests, report status |
| AC4 | Failing test or lint error → red status check, failure visible in the log |
| AC5 | README explains install, run and test |

**Out of scope**

- Domain models and endpoints for tenants, properties, leases and payments (REN-3 to REN-5).
- The knowledge base (`kb/index.py`, the `kb` MCP server, `search_kb`). It is a separate piece of work.
- Branch protection settings on GitHub. Making the check *required* is a repository
  setting, not code (see §8).

## 3. Context and constraints

- The repository is empty apart from `CLAUDE.md`. There are no existing patterns or designs to reuse,
  and `search_kb` isn't available yet.
- The stack comes from CLAUDE.md: Python 3.12, FastAPI, SQLAlchemy + SQLite, Pydantic,
  pytest + pytest-cov + httpx, ruff. **No other libraries.** (The AC3/AC4 workflow test parses YAML.
  PyYAML is already installed as a transitive dependency of uvicorn's `standard` extra, so it is pinned
  in `[dev]` explicitly rather than being a new library choice. The LLD will confirm this.)
- Local machine default Python is 3.15. The venv will use 3.12 (`uv python install 3.12`)
  to match CI.

## 4. Architecture

```
            ┌──────────────── app/ ────────────────┐
 HTTP ──▶   │ main.py   create_app() factory        │
            │   ├─ exception handler: validation→400│
            │   └─ include_router(health.router)    │
            │ routers/health.py   GET /health        │
            │ db.py     engine/session factory       │──▶ SQLite (file; URL from env)
            │ models.py / schemas.py  (empty bases)  │
            │ services/  (empty package)             │
            └────────────────────────────────────────┘
```

- **App factory** `create_app(settings=None)` returns a configured `FastAPI` instance, and
  `app = create_app()` is the module-level ASGI target for uvicorn. With a factory, functional
  tests can build an app pointed at a temp SQLite file for each test.
- **Health router**: `GET /health` → `{"status": "ok"}`. It is static and needs no DB,
  so the service stays up even if there is no database yet.
- **DB module**: SQLAlchemy 2.x `create_engine` + `sessionmaker`, a declarative `Base` and a
  `get_session` FastAPI dependency. The DB URL comes from the `RENTLEDGER_DATABASE_URL` env var, with
  `sqlite:///./rentledger.db` as the default. No tables yet. This sets the pattern REN-3 builds on.
- **Validation → 400**: a `RequestValidationError` handler returns 400 and names the invalid
  fields (CLAUDE.md API conventions). It is set up here so every later router inherits it. The health
  endpoint has no input, so this handler gets its tests through a small test-only route in the test suite.
- **Clock**: an injectable `Clock` (`today() -> date`) is set up now in `app/services/clock.py`
  so later business logic never calls `date.today()` directly.

## 5. Repository layout (after REN-2)

```
pyproject.toml          # deps, [dev] extra, ruff, pytest + coverage config
README.md               # install / run / test / lint (AC5)
.gitignore
.github/workflows/ci.yml
app/__init__.py, main.py, db.py, models.py, schemas.py
app/routers/__init__.py, health.py
app/services/__init__.py, clock.py
tests/conftest.py       # `jira` marker, `--jira REN-n` filter, app/client fixtures
tests/unit/...
tests/functional/...
docs/design/REN-2-hld.md, REN-2-lld.md (next stage)
```

## 6. Tooling and quality gates

- **pyproject.toml**: setuptools build, runtime deps (`fastapi`, `uvicorn[standard]`,
  `sqlalchemy`, `pydantic`) and the `[dev]` extra (`pytest`, `pytest-cov`, `httpx`, `ruff`, `pyyaml`).
- **pytest**: `addopts = --cov=app --cov-branch --cov-report=term-missing --cov-fail-under=90`,
  `testpaths = ["tests"]`, and the `jira(key)` marker registered with `--strict-markers`.
- **`--jira REN-n`**: a `conftest.py` option that deselects tests without a matching `jira` marker.
- **ruff**: `ruff check` + `ruff format --check`, target `py312`, line length 100.

## 7. CI design (AC3, AC4)

`.github/workflows/ci.yml`:

- Triggers: `pull_request` on `main`, plus `push` to `main`.
- One job, `test`, on `ubuntu-latest`: checkout → `actions/setup-python` (3.12, pip cache)
  → `pip install -e ".[dev]"` → `ruff check .` → `ruff format --check .` → `pytest`.
- Each step fails on non-zero exit, so a failing lint or test turns the job, and the PR check, red,
  and the step log shows the failure (AC4). No `continue-on-error` anywhere.

## 8. Test strategy per AC

Every test carries `@pytest.mark.jira("REN-2")` and the AC number in its name.

| AC | Unit | Functional |
|----|------|-----------|
| AC1 | `create_app()` registers `/health`; the settings default for the DB URL | `GET /health` → 200 `{"status":"ok"}` via TestClient; smoke start of real `uvicorn` subprocess hitting `/health` |
| AC2 | — | Subprocess `pytest -m "not subprocess_suite" -q` exits 0. The self-check is guarded so it doesn't recurse |
| AC3 | Parse `ci.yml`: has a `pull_request` trigger on `main` and steps for install, ruff check, ruff format, pytest | — |
| AC4 | Parse `ci.yml`: no `continue-on-error`, and the lint and test steps aren't `|| true`-masked | — |
| AC5 | README contains the install, run (`uvicorn app.main:app`) and test (`pytest`) commands | — |
| Cross-cutting | Validation handler formats field names | Bad input on a test route → 400 naming the field |

**Manual verification (AC3/AC4)**: once the PR is open, confirm the check is green. Then push a temporary
failing commit (or open a throwaway PR), confirm the check goes red, and confirm the log shows the failure.
If the check should *block* merging, a repository admin has to mark it required in branch protection.

## 9. Risks and open points

- **The Jira workflow is missing statuses.** REN only has To Do / In Progress / Done. CLAUDE.md
  expects HLD Review, LLD Review and In Review. Until those are added, the issue stays in To Do
  during design, and a mapping for "In Review" has to be agreed.
- **Python version drift**: 3.15 locally vs 3.12 in CI. Mitigation: build the venv with 3.12.
- **Self-running test suite (AC2)** can be slow or recursive. It is guarded by a marker and
  excluded from the inner run.
