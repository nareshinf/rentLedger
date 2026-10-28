# RentLedger — project rules for Claude

RentLedger is a small rent-tracking API (tenants, properties, leases, payments, balances).
It is a hands-on SDLC exercise: every change is driven by a Jira issue in project **REN**
on nareshmalhotra.atlassian.net.

## Stack
- Python 3.12, FastAPI, SQLAlchemy + SQLite, Pydantic
- pytest, pytest-cov, httpx (FastAPI TestClient), ruff
- Knowledge base: ChromaDB + sentence-transformers, exposed via the `kb` MCP server (`search_kb`)

## Commands
- Install: `python -m venv .venv && source .venv/bin/activate && pip install -e ".[dev]"`
- Run: `uvicorn app.main:app --reload`  (health check: `GET /health` → `{"status": "ok"}`)
- Test: `pytest`  (coverage gate is configured in pyproject.toml)
- Tests for one issue: `pytest --jira REN-<n>`
- Lint: `ruff check . && ruff format --check .`
- Re-index knowledge base: `python kb/index.py`

## Layout
- `app/` — `main.py`, `db.py`, `models.py`, `schemas.py`, `routers/`, `services/`
- `tests/unit/` — business rules, helpers, KB chunker; no network, in-memory SQLite
- `tests/functional/` — endpoints end to end via TestClient on a temp SQLite file per test
- `docs/` — overview, glossary, architecture, coding standards, testing strategy, `adr/`
- `docs/design/REN-<n>-hld.md`, `docs/design/REN-<n>-lld.md` — designs per issue
- `kb/` — `index.py`, `server.py`
- `.claude/skills/` — `jira-hld`, `jira-lld`, `jira-implement`, `jira-bugfix`

## Jira workflow (non-negotiable)
1. No code change without a REN issue key. If asked to change code with no issue, propose
   creating one first.
2. Read the issue and its acceptance criteria (AC) before doing anything. If ACs are missing
   or contradict existing behaviour, comment on the issue and stop.
3. Statuses: To Do → HLD Review → LLD Review → In Progress → In Review → Done.
4. Human gates: do not write an LLD without label `hld-approved`; do not implement without
   label `lld-approved`. Never move an issue to Done; a human merges.
5. Branch: `REN-<n>-<short-slug>`. Every commit message starts `REN-<n>: `.
6. Post a summary comment on the issue at the end of each stage (design summary + file path,
   or the test-evidence table).

## Before designing or coding
- Run `search_kb` for the issue's key terms and read related designs in `docs/design/`.
- Reuse existing patterns in `app/services/` and `app/routers/`; do not add new libraries
  without noting why in the HLD.

## API conventions (set by REN-2 to REN-5)
- Request validation errors → **400** with the invalid field(s) named. FastAPI's default is
  422, so a handler maps `RequestValidationError` to 400.
- A body that references a missing tenant/property → **422** naming the missing reference.
- Unknown id in the path → **404**. Overlapping lease or delete-while-referenced → **409**.
- Create → 201 with the new record including `id`; read/update → 200.
- Lease due day is 1–28. A lease has status `active` or `ended`.

## Money and dates
- Money is exact: `Decimal` in code, `Numeric(12, 2)` in the database. Never use float.
- Rent accrues once per due date from lease start; nothing accrues after the lease end date.
- Balance = charged − paid; negative balance means credit. `asOf` counts only charges due and
  payments made on or before that date.
- Get "today" from an injectable clock, never call `date.today()` inside business logic,
  so tests can freeze time.

## Testing rules
- Every AC has at least one test, marked `@pytest.mark.jira("REN-<n>")`, with the AC number
  in the name, e.g. `test_ac3_due_day_outside_range_returns_400`.
- Business rules get unit tests; every endpoint and status code gets a functional test.
- Write tests from the LLD test plan first and confirm they fail before implementing.
- `pytest` must pass with coverage ≥ 90% (branch coverage) and `ruff` must be clean
  before every commit.
- No real network or email in tests: use fakes (e.g. a fake `Notifier`).

## Definition of done (for In Review)
- All ACs covered and passing; coverage gate met; lint clean.
- `docs/` updated if behaviour or terms changed; `python kb/index.py` run.
- PR opened titled `REN-<n>: <summary>`.
- Evidence comment on the issue: AC → test(s) → pass/fail, coverage %, PR link.
