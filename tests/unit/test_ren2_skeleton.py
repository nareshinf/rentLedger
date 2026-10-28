from datetime import date

import pytest
from sqlalchemy import text

from app.db import DATABASE_URL_ENV, DEFAULT_DATABASE_URL, get_database_url, make_engine
from app.errors import format_validation_errors
from app.main import create_app
from app.services.clock import FixedClock, SystemClock, get_clock

pytestmark = pytest.mark.jira("REN-2")


def test_ac1_create_app_registers_health_route():
    app = create_app("sqlite://")
    assert "get" in app.openapi()["paths"]["/health"]


def test_ac1_database_url_defaults_and_env_override():
    assert get_database_url({}) == DEFAULT_DATABASE_URL
    assert get_database_url({DATABASE_URL_ENV: "sqlite:///x.db"}) == "sqlite:///x.db"


def test_ac1_sqlite_engine_allows_cross_thread():
    engine = make_engine("sqlite://")
    with engine.connect() as conn:
        assert conn.execute(text("SELECT 1")).scalar() == 1


def test_format_validation_errors_strips_location_prefix():
    errors = [
        {"loc": ("body", "name"), "msg": "Field required"},
        {"loc": ("query", "limit"), "msg": "Input should be a valid integer"},
        {"loc": ("body", "address", "city"), "msg": "Field required"},
        {"loc": ("body",), "msg": "Field required"},
    ]
    assert format_validation_errors(errors) == [
        {"field": "name", "message": "Field required"},
        {"field": "limit", "message": "Input should be a valid integer"},
        {"field": "address.city", "message": "Field required"},
        {"field": "body", "message": "Field required"},
    ]


def test_fixed_clock_returns_given_day():
    assert FixedClock(date(2026, 1, 15)).today() == date(2026, 1, 15)


def test_system_clock_returns_today():
    assert get_clock().today() == date.today()
    assert isinstance(get_clock(), SystemClock)
