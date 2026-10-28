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
