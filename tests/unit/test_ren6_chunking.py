import textwrap

import pytest

from kb.chunking import chunk_file, kind_for, markdown_chunks, python_chunks

pytestmark = pytest.mark.jira("REN-6")


def _md(text: str) -> str:
    return textwrap.dedent(text).lstrip()


def test_ac2_markdown_split_by_heading_with_trail():
    chunks = markdown_chunks(
        "docs/design/x.md",
        _md("""
        # A
        intro
        ## B
        about b
        ### C
        about c
        ## D
        about d
        """),
    )
    assert [c.title for c in chunks] == ["A", "A › B", "A › B › C", "A › D"]
    assert chunks[1].text == "## B\nabout b"
    assert {c.kind for c in chunks} == {"design"}
    assert {c.path for c in chunks} == {"docs/design/x.md"}


def test_ac2_markdown_ignores_hash_lines_in_code_fences():
    chunks = markdown_chunks(
        "docs/guide.md",
        _md("""
        # Setup
        ```bash
        # not a heading
        pip install
        ```
        ~~~
        ## also not a heading
        ~~~
        # Next
        body
        """),
    )
    assert [c.title for c in chunks] == ["Setup", "Next"]
    assert "# not a heading" in chunks[0].text


def test_ac2_markdown_preamble_titled_with_file_name():
    chunks = markdown_chunks("docs/guide.md", "Intro line\n\n# First\nbody\n")
    assert [(c.title, c.text) for c in chunks] == [
        ("guide.md", "Intro line"),
        ("First", "# First\nbody"),
    ]


def test_ac2_markdown_skips_empty_sections():
    chunks = markdown_chunks("docs/guide.md", "# A\n\n## B\nbody\n## C\n\n")
    assert [c.title for c in chunks] == ["A › B"]


def test_ac2_python_one_chunk_per_function_and_class():
    source = _md('''
        import os


        def plain(a):
            return a


        async def fetch():
            return 1


        @decorator
        def wrapped():
            pass


        class Thing:
            """Doc."""

            def method(self):
                return 2

            def other(self):
                return 3
        ''')
    chunks = python_chunks("app/services/x.py", source)
    by_title = {c.title: c for c in chunks}
    assert set(by_title) == {"plain", "fetch", "wrapped", "Thing"}
    assert by_title["wrapped"].text.startswith("@decorator\ndef wrapped")
    assert "def method" in by_title["Thing"].text and "def other" in by_title["Thing"].text
    assert by_title["fetch"].text.startswith("async def fetch")
    assert {c.kind for c in chunks} == {"code"}


def test_ac2_python_module_chunk_holds_constants_not_imports():
    source = _md('''
        """Schemas."""
        from decimal import Decimal

        Money = Decimal
        LIMIT = 28


        def f():
            pass
        ''')
    chunks = python_chunks("app/schemas.py", source)
    module = next(c for c in chunks if c.title == "<module>")
    assert "Schemas." in module.text
    assert "Money = Decimal" in module.text and "LIMIT = 28" in module.text
    assert "import" not in module.text
    assert "def f" not in module.text


def test_ac2_python_module_chunk_skipped_when_only_imports():
    chunks = python_chunks("app/x.py", "import os\n\n\ndef f():\n    pass\n")
    assert [c.title for c in chunks] == ["f"]


@pytest.mark.parametrize(
    ("path", "kind"),
    [
        ("docs/design/REN-5-hld.md", "design"),
        ("docs/guide.md", "doc"),
        ("docs/sub/notes.md", "doc"),
        ("app/services/balance.py", "code"),
    ],
)
def test_ac2_kind_for_paths(path, kind):
    assert kind_for(path) == kind


def test_ac2_kind_for_other_paths_rejected():
    with pytest.raises(ValueError):
        kind_for("tests/test_x.py")


def test_ac2_chunk_ids_stable_and_unique():
    text = "# Notes\na\n# Notes\nb\n"
    first = markdown_chunks("docs/guide.md", text)
    again = markdown_chunks("docs/guide.md", text)
    assert [c.ordinal for c in first] == [0, 1]
    assert [c.id for c in first] == [c.id for c in again]
    assert len({c.id for c in first}) == 2


def test_ac2_chunk_file_dispatches_on_suffix():
    assert chunk_file("docs/guide.md", "# A\nbody\n")[0].title == "A"
    assert chunk_file("app/x.py", "def f():\n    pass\n")[0].title == "f"
    with pytest.raises(ValueError):
        chunk_file("app/notes.txt", "hello")


def test_ac2_python_syntax_error_propagates():
    with pytest.raises(SyntaxError):
        python_chunks("app/broken.py", "def broken(:\n")
