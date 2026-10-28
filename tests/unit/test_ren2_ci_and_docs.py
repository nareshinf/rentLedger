import re

import pytest
import yaml

pytestmark = pytest.mark.jira("REN-2")


@pytest.fixture
def workflow(root):
    return yaml.safe_load((root / ".github" / "workflows" / "ci.yml").read_text())


@pytest.fixture
def steps(workflow):
    return [step for job in workflow["jobs"].values() for step in job["steps"]]


def _triggers(workflow):
    # PyYAML (YAML 1.1) reads the bare key `on` as boolean True.
    return workflow.get("on", workflow.get(True))


def test_ac3_ci_triggers_on_pull_request_to_main(workflow):
    assert "main" in _triggers(workflow)["pull_request"]["branches"]


def test_ac3_ci_installs_lints_and_tests(steps):
    commands = [step.get("run", "") for step in steps]
    expected = ['pip install -e ".[dev]"', "ruff check", "ruff format --check", "pytest"]
    positions = [next(i for i, c in enumerate(commands) if e in c) for e in expected]
    assert positions == sorted(positions)


def test_ac3_ci_uses_python_312(steps):
    setup = next(s for s in steps if s.get("uses", "").startswith("actions/setup-python"))
    assert str(setup["with"]["python-version"]) == "3.12"


def test_ac4_ci_failures_are_not_masked(workflow, steps):
    for job in workflow["jobs"].values():
        assert "continue-on-error" not in job
    for step in steps:
        assert "continue-on-error" not in step
        assert not re.search(r"\|\|\s*true|;\s*exit 0", step.get("run", ""))


def test_ac5_readme_documents_install_run_test(root):
    readme = (root / "README.md").read_text()
    assert 'pip install -e ".[dev]"' in readme
    assert "uvicorn app.main:app" in readme
    assert "pytest" in readme
