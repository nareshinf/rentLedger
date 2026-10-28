import os
import socket
import subprocess
import sys
import time
from typing import Annotated

import httpx
import pytest
from fastapi import Depends
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db import DATABASE_URL_ENV, get_session

pytestmark = pytest.mark.jira("REN-2")


class _Item(BaseModel):
    name: str


def test_ac1_health_returns_ok(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_ac1_session_dependency_yields_working_session(app, client):
    @app.get("/_test/db")
    def db_check(session: Annotated[Session, Depends(get_session)]):
        return {"value": session.execute(text("SELECT 1")).scalar()}

    response = client.get("/_test/db")
    assert response.status_code == 200
    assert response.json() == {"value": 1}


def test_ac1_validation_error_returns_400_naming_field(app, client):
    @app.post("/_test/items")
    def create_item(item: _Item):
        return item

    response = client.post("/_test/items", json={})
    assert response.status_code == 400
    body = response.json()
    assert body["detail"] == "Validation failed"
    assert body["errors"][0]["field"] == "name"


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_ac1_service_starts_with_uvicorn(root, tmp_path):
    port = _free_port()
    env = {**os.environ, DATABASE_URL_ENV: f"sqlite:///{tmp_path / 'smoke.db'}"}
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--port", str(port)],
        cwd=root,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        deadline = time.monotonic() + 15
        while True:
            try:
                response = httpx.get(f"http://127.0.0.1:{port}/health", timeout=1)
                break
            except httpx.TransportError:
                if time.monotonic() > deadline or proc.poll() is not None:
                    pytest.fail("uvicorn did not serve /health within 15 s")
                time.sleep(0.2)
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}
    finally:
        proc.terminate()
        proc.wait(timeout=10)


@pytest.mark.self_run
def test_ac2_test_suite_exits_zero(root):
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-m",
            "not self_run",
            "--no-cov",
            "-q",
            "-p",
            "no:cacheprovider",
        ],
        cwd=root,
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert result.returncode == 0, result.stdout + result.stderr
