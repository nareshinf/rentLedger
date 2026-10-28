from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parent.parent


def pytest_addoption(parser):
    parser.addoption(
        "--jira", action="store", default=None, help="Only run tests marked jira(KEY)."
    )


def pytest_configure(config):
    config.addinivalue_line(
        "markers", "jira(key): Jira issue whose acceptance criteria the test covers"
    )
    config.addinivalue_line("markers", "self_run: runs the test suite in a subprocess")


def pytest_collection_modifyitems(config, items):
    key = config.getoption("--jira")
    if not key:
        return
    selected, deselected = [], []
    for item in items:
        keys = {m.args[0] for m in item.iter_markers("jira") if m.args}
        (selected if key in keys else deselected).append(item)
    if deselected:
        config.hook.pytest_deselected(items=deselected)
        items[:] = selected


@pytest.fixture
def root() -> Path:
    return ROOT


@pytest.fixture
def app(tmp_path):
    from app.main import create_app

    return create_app(f"sqlite:///{tmp_path / 'test.db'}")


@pytest.fixture
def client(app):
    with TestClient(app) as c:
        yield c


@pytest.fixture
def db_session():
    from sqlalchemy.pool import StaticPool

    from app.db import create_tables, make_engine, make_session_factory

    engine = make_engine("sqlite://", poolclass=StaticPool)
    create_tables(engine)
    session = make_session_factory(engine)()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()
