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

The database defaults to `./rentledger.db`. To use a different database, set `RENTLEDGER_DATABASE_URL`, for example `sqlite:////tmp/rentledger.db`.

## API

| Method | Path | Success | Errors |
|--------|------|---------|--------|
| GET | `/health` | 200 `{"status": "ok"}` | |
| POST | `/properties`, `/tenants` | 201 with the new record, including `id` | 400 |
| GET | `/properties`, `/tenants` | 200 list, ordered by `id` | |
| GET | `/properties/{id}`, `/tenants/{id}` | 200 | 400 (non-integer id), 404 |
| PATCH | `/properties/{id}`, `/tenants/{id}` | 200 (partial update) | 400, 404 |
| DELETE | `/properties/{id}`, `/tenants/{id}` | 204, no body | 404, 409 if a lease references the record |

- Property fields are `name` and `address`.
- Tenant fields are `full_name`, `email` and an optional `phone`. Emails are validated and stored in lower case.
- A validation error returns 400 with an `errors` list, and each entry names its `field`.

Interactive docs are served at `/docs` while the service is running.

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
