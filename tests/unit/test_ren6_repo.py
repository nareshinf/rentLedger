import json
import subprocess
import tomllib

import pytest

pytestmark = pytest.mark.jira("REN-6")


def test_ac6_kb_dir_is_git_ignored(root):
    assert ".kb/" in (root / ".gitignore").read_text().splitlines()
    result = subprocess.run(["git", "check-ignore", "-q", ".kb/chroma.sqlite3"], cwd=root)
    assert result.returncode == 0


def test_ac6_coverage_gate_includes_kb(root):
    config = tomllib.loads((root / "pyproject.toml").read_text())
    addopts = config["tool"]["pytest"]["ini_options"]["addopts"]
    assert "--cov=kb" in addopts
    assert "--cov=app" in addopts
    assert "--cov-fail-under=90" in addopts


def test_mcp_json_registers_kb_server(root):
    servers = json.loads((root / ".mcp.json").read_text())["mcpServers"]
    assert servers["kb"]["args"] == ["kb/server.py"]
    assert servers["kb"]["env"]["HF_HUB_OFFLINE"] == "1"
