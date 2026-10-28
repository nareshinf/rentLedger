import os
import subprocess
import sys

import pytest

from kb import index
from kb.embedding import HashingEmbedder
from kb.store import KnowledgeBase

pytestmark = pytest.mark.jira("REN-6")

FILES = {
    "docs/design/x.md": "# Balance\nbalance equals charged minus paid\n## Notes\nmore notes\n",
    "docs/guide.md": "# Guide\nhow to install and run\n",
    "app/a.py": "RATE = 1\n\n\ndef compute():\n    return RATE\n\n\nclass Thing:\n    pass\n",
    # decoys outside the globs
    "README.md": "# Readme\nnot indexed\n",
    "tests/t.py": "def test_x():\n    pass\n",
    "app/notes.txt": "not python\n",
}


@pytest.fixture
def repo(tmp_path):
    for rel, text in FILES.items():
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    return tmp_path


def _paths(root):
    hits = KnowledgeBase(root / ".kb", HashingEmbedder()).search("anything", k=20)
    return {h.path for h in hits}


def test_ac1_index_script_builds_kb_in_dot_kb(root, repo):
    env = {**os.environ, "RENTLEDGER_KB_EMBEDDER": "hashing"}
    result = subprocess.run(
        [sys.executable, "kb/index.py", "--root", str(repo)],
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, result.stderr
    assert (repo / ".kb").is_dir()
    assert "Indexed 6 chunks from 3 files" in result.stdout
    assert _paths(repo) == {"docs/design/x.md", "docs/guide.md", "app/a.py"}


def test_ac1_main_in_process_reports_counts(repo, capsys):
    assert index.main(["--root", str(repo)], embedder=HashingEmbedder()) == 0
    out = capsys.readouterr().out
    assert "Indexed 6 chunks from 3 files into .kb/ (removed 0 stale)" in out


def test_ac1_collect_files_honours_globs(repo):
    assert index.collect_files(repo) == ["app/a.py", "docs/design/x.md", "docs/guide.md"]


def test_ac3_reindex_no_duplicates_and_deleted_file_disappears(repo, capsys):
    embedder = HashingEmbedder()
    index.main(["--root", str(repo)], embedder=embedder)
    index.main(["--root", str(repo)], embedder=embedder)
    assert "Indexed 6 chunks from 3 files into .kb/ (removed 0 stale)" in capsys.readouterr().out
    assert KnowledgeBase(repo / ".kb", embedder).count() == 6

    (repo / "docs/guide.md").unlink()
    index.main(["--root", str(repo)], embedder=embedder)
    assert "Indexed 5 chunks from 2 files into .kb/ (removed 1 stale)" in capsys.readouterr().out
    assert "docs/guide.md" not in _paths(repo)


def test_ac1_unparseable_python_file_is_skipped_and_reported(repo, capsys):
    (repo / "app/broken.py").write_text("def broken(:\n")
    assert index.main(["--root", str(repo)], embedder=HashingEmbedder()) == 0
    out = capsys.readouterr().out
    assert "Skipped app/broken.py" in out
    assert "app/broken.py" not in _paths(repo)


def test_index_without_sentence_transformers_exits_1_with_hint(repo, monkeypatch, capsys):
    from kb import embedding

    monkeypatch.delenv("RENTLEDGER_KB_EMBEDDER", raising=False)
    monkeypatch.setitem(sys.modules, "sentence_transformers", None)
    embedding.default_embedder.cache_clear()
    try:
        assert index.main(["--root", str(repo)]) == 1
    finally:
        embedding.default_embedder.cache_clear()
    assert "pip install -e '.[kb]'" in capsys.readouterr().err
