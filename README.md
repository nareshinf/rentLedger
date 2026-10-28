# RentLedger

RentLedger is a small rent-tracking API for tenants, properties, leases, payments and balances. It uses FastAPI, SQLAlchemy and SQLite.

## Requirements

- Python 3.12

## Install

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## Run

```bash
uvicorn app.main:app --reload
```

Check that the service is up:

```bash
curl http://127.0.0.1:8000/health
# {"status":"ok"}
```

The database defaults to `./rentledger.db`. There are no migrations yet. When the schema changes (for example REN-4 added lease columns), delete your local `rentledger.db`; it is recreated on the next start. To use a different database, set `RENTLEDGER_DATABASE_URL`, for example `sqlite:////tmp/rentledger.db`.

## API

| Method | Path | Success | Errors |
|--------|------|---------|--------|
| GET | `/health` | 200 `{"status": "ok"}` | |
| POST | `/properties`, `/tenants` | 201 with the new record, including `id` | 400 |
| GET | `/properties`, `/tenants` | 200 list, ordered by `id` | |
| GET | `/properties/{id}`, `/tenants/{id}` | 200 | 400 (non-integer id), 404 |
| PATCH | `/properties/{id}`, `/tenants/{id}` | 200 (partial update) | 400, 404 |
| DELETE | `/properties/{id}`, `/tenants/{id}` | 204, no body | 404, 409 if a lease references the record |
| POST | `/leases` | 201 with the new lease, `status: "active"` | 400, 422 (unknown tenant/property), 409 (overlap) |
| GET | `/leases?tenantId=&propertyId=` | 200 list, filters optional and combined | 400 (non-integer filter) |
| GET | `/leases/{id}` | 200 | 404 |
| POST | `/leases/{id}/end` with `{"end_date": "YYYY-MM-DD"}` | 200, `status: "ended"` | 400, 404, 409 (already ended) |
| POST | `/leases/{id}/payments` | 201 with the payment | 400, 404 |
| GET | `/leases/{id}/payments` | 200 list, ordered by `paid_on` | 404 |
| GET | `/leases/{id}/balance?asOf=YYYY-MM-DD` | 200 balance (`asOf` defaults to today) | 400 (bad date), 404 |

- Property fields are `name` and `address`.
- Tenant fields are `full_name`, `email` and an optional `phone`. Emails are validated and stored in lower case.
- A validation error returns 400 with an `errors` list, and each entry names its `field`.
- A lease has `tenant_id`, `property_id`, `start_date`, an optional `end_date` (no end date means open-ended), `monthly_rent` and `due_day` (1–28).
  - `monthly_rent` is an exact amount above 0 with at most 2 decimal places, and is returned as a string such as `"1200.00"`.
  - Rent falls due on `due_day` each month, from the first due day on or after the start date up to and including the end date.
- Two leases on the same property can't overlap. This applies to ended leases too, for the dates they covered.
- `POST /leases/{id}/end` can only keep or bring forward an existing end date.
- A payment has `amount` (above 0, at most 2 decimal places), `paid_on` (not in the future), and an optional `method` and `note`.
  - Ended leases still accept payments.
- The balance is calculated as follows, with every amount an exact decimal returned as a string:
  - `charges_due` is the number of due dates on or before `asOf`.
  - `charged` = `charges_due` × `monthly_rent`.
  - `paid` is the total of payments made on or before `asOf`.
  - `balance` = `charged` − `paid`. A negative balance is a credit.

Interactive docs are served at `/docs` while the service is running.

## Knowledge base

A local semantic index of `docs/**/*.md` and `app/**/*.py`. Claude Code can query it through the `search_kb` MCP tool.

```bash
pip install -e ".[kb]"   # adds sentence-transformers (and torch); needed once
python kb/index.py       # build or refresh .kb/ (re-run after changing docs or code)
```

- **Indexing:**
  - The first run downloads the `all-MiniLM-L6-v2` embedding model, about 90 MB. Later runs reuse the cached copy.
  - Re-running is idempotent: changed sections are updated, and chunks from deleted files are removed.
  - `.kb/` is git-ignored.
- **Search:**
  - `.mcp.json` registers the `kb` server, so Claude Code in this repo gets `search_kb(query, k=5, kind=None)`.
  - `kind` is `doc`, `design` or `code`.
  - It runs offline (`HF_HUB_OFFLINE=1`) using the cached model.
- **Tests:**
  - Tests and CI use a deterministic stand-in embedder (`RENTLEDGER_KB_EMBEDDER=hashing`), so they need no model and no network.
  - The real-model relevance check is marked `kb_model`. It runs only when `[kb]` is installed and the model is cached, and is skipped otherwise:
    `HF_HUB_OFFLINE=1 pytest -m kb_model`.

## Test

```bash
pytest                 # full suite; fails below 90% branch coverage
pytest --jira REN-2    # only the tests for one Jira issue
```

## Lint

```bash
ruff check . && ruff format --check .
```

## CI

GitHub Actions (`.github/workflows/ci.yml`) runs on every pull request to `main` and on every push to `main`. It installs dependencies, runs ruff lint and the format check, then runs `pytest`. If any step fails, the check turns red on the PR, and the failing step's log shows the error.
