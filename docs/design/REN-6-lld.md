# REN-6 — Knowledge base and search_kb tool: Low-Level Design

- **Issue:** [REN-6](https://nareshmalhotra.atlassian.net/browse/REN-6)
- **HLD:** [REN-6-hld.md](REN-6-hld.md) (`hld-approved`; K1–K4 recommendations accepted)
- **Stage:** LLD (awaiting `lld-approved`)

**API check done for this LLD** (chromadb 1.5.9 and mcp 2.3.0 installed into the dev venv):
- In `mcp` 2.x, **`FastMCP` was renamed `MCPServer`** (`from mcp.server.mcpserver import MCPServer`). The HLD's "FastMCP" means this class.
- `ToolError` (`mcp.server.mcpserver.exceptions`) is raised from `call_tool` in-process, and becomes an error result over MCP.
- Chroma collection names need at least 3 characters. Cosine distance (`hnsw:space`), `where` filters and `delete(ids)` all behave as the design assumes.

## 1. Files

| Path | Change |
|------|--------|
| `kb/__init__.py` | package marker |
| `kb/chunking.py` | `Chunk`, `kind_for`, `markdown_chunks`, `python_chunks`, `chunk_file` |
| `kb/embedding.py` | `Embedder` protocol, `HashingEmbedder`, `SentenceTransformerEmbedder`, `default_embedder()` |
| `kb/store.py` | `KnowledgeBase` (`sync`, `search`, `count`), `Hit`, `SyncResult`, `EmptyIndexError`, `EmbedderMismatchError` |
| `kb/index.py` | CLI `python kb/index.py [--root PATH]` |
| `kb/server.py` | `MCPServer("kb")` with the `search_kb` tool; `python kb/server.py` runs stdio |
| `.mcp.json` | registers the `kb` server (K4) |
| `.gitignore` | add `.kb/` |
| `pyproject.toml` | see §6 |
| `tests/conftest.py` | register the `kb_model` marker |
| `tests/unit/test_ren6_*.py`, `tests/functional/test_ren6_*.py` | §7 |
| `README.md` | "Knowledge base" section |

## 2. Chunking (`kb/chunking.py`)

```python
@dataclass(frozen=True)
class Chunk:
    path: str        # repo-relative POSIX path
    title: str       # heading trail, symbol name, or "<module>"
    kind: str        # "doc" | "design" | "code"
    text: str
    ordinal: int     # nth chunk with this (path, title); keeps ids stable
    @property
    def id(self) -> str:  # sha1(f"{path}\0{title}\0{ordinal}").hexdigest()

def kind_for(path: str) -> str
    # docs/design/** → "design"; docs/** → "doc"; app/** → "code"; else ValueError

def markdown_chunks(path: str, text: str) -> list[Chunk]
    # ATX heading regex ^(#{1,6})\s+(.+?)\s*#*\s*$ ; lines inside ``` / ~~~ fences are never headings
    # heading stack by level → title = " › ".join(trail)
    # chunk text = the heading line + body up to the next heading of any level
    # text before the first heading → title = file name (e.g. "REN-5-hld.md")
    # sections whose body (excluding the heading line) is blank are skipped

def python_chunks(path: str, text: str) -> list[Chunk]
    # ast.parse; for each top-level FunctionDef / AsyncFunctionDef / ClassDef:
    #   text = source lines from the first decorator (or def/class) to end_lineno; title = node.name
    # "<module>" chunk (K3): module docstring + source of every other top-level statement except
    #   Import / ImportFrom, joined with newlines; skipped when empty
    # SyntaxError → propagate (the indexer reports it and skips that file)

def chunk_file(path: str, text: str) -> list[Chunk]   # dispatch on suffix .md / .py
```

## 3. Embeddings (`kb/embedding.py`)

```python
class Embedder(Protocol):
    name: str
    def embed(self, texts: list[str]) -> list[list[float]]: ...

class HashingEmbedder:                     # deterministic, no network, no torch: tests and CI
    name = "hashing-v1"; dim = 512
    # tokens = re.findall(r"[a-z0-9]+", text.lower()); bucket = sha1(token) % dim; counts; L2-normalised
    # an all-zero vector (no tokens) gets 1.0 in bucket 0, so cosine distance is always defined

class SentenceTransformerEmbedder:         # real model; `# pragma: no cover` (K2), exercised by kb_model test
    def __init__(self, model: str = "all-MiniLM-L6-v2")   # lazy import; ImportError → KbDependencyError
    name = f"st:{model}"                                  #   "pip install -e '.[kb]'"
    # embed → model.encode(texts, normalize_embeddings=True).tolist()

@functools.cache
def default_embedder() -> Embedder
    # RENTLEDGER_KB_EMBEDDER=hashing → HashingEmbedder(); otherwise SentenceTransformerEmbedder()
```
What gets embedded is `f"{chunk.title}\n{chunk.text}"`, so the heading trail and symbol name add context. The stored document is `chunk.text`.

## 4. Store (`kb/store.py`)

```python
COLLECTION = "rentledger"

@dataclass(frozen=True) class Hit:        path, title, kind, text, score: float   # 1 − cosine distance, 3 dp
@dataclass(frozen=True) class SyncResult: indexed: int, removed: int
class EmptyIndexError(Exception)          # "Knowledge base is empty — run `python kb/index.py`"
class EmbedderMismatchError(Exception)    # "Index built with X but searching with Y — re-run `python kb/index.py`"

class KnowledgeBase:
    def __init__(self, path: Path, embedder: Embedder)   # chromadb.PersistentClient(path=str(path))

    def sync(self, chunks: list[Chunk]) -> SyncResult
        # duplicate ids → ValueError
        # collection = get_or_create(COLLECTION, metadata={"hnsw:space": "cosine", "embedder": name},
        #                            embedding_function=None)
        # if collection.metadata["embedder"] != embedder.name: delete_collection + recreate
        # existing = set(collection.get(include=[])["ids"])
        # upsert(ids, embeddings, documents=text, metadatas={path, title, kind}) in batches of 256
        # stale = existing − current ids → collection.delete(ids=stale)
        # return SyncResult(indexed=len(chunks), removed=len(stale))

    def search(self, query: str, k: int, kind: str | None = None) -> list[Hit]
        # read-only: get_collection; missing or count()==0 → EmptyIndexError
        # metadata embedder ≠ self.embedder.name → EmbedderMismatchError (never rebuilds on read)
        # query(query_embeddings=[embed(query)], n_results=min(k, count),
        #       where={"kind": kind} if kind else None, include=[documents, metadatas, distances])

    def count(self) -> int                                # 0 when the collection doesn't exist
```

## 5. CLI and MCP server

### `kb/index.py`
```python
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:      # `python kb/index.py` puts kb/ on sys.path, not the repo root
    sys.path.insert(0, str(ROOT))
from kb.chunking import chunk_file  # noqa: E402   (same for store / embedding)

GLOBS = ("docs/**/*.md", "app/**/*.py")
def collect_files(root: Path) -> list[str]        # sorted repo-relative POSIX paths matching GLOBS
def build_chunks(root: Path) -> tuple[list[Chunk], list[str]]   # (chunks, skipped files with reasons)
def main(argv: list[str] | None = None, embedder: Embedder | None = None) -> int
    # --root (default ROOT); KnowledgeBase(root / ".kb", embedder or default_embedder()).sync(chunks)
    # prints: "Indexed 312 chunks from 28 files into .kb/ (removed 4 stale)" and any skipped files
    # exit 0; KbDependencyError → message on stderr, exit 1
if __name__ == "__main__": raise SystemExit(main())
```

### `kb/server.py`
```python
KB_PATH = Path(os.environ.get("RENTLEDGER_KB_PATH", ROOT / ".kb"))
KINDS = ("doc", "design", "code")
server = MCPServer("kb", instructions="Semantic search over RentLedger docs, designs and code.")


@server.tool()
def search_kb(query: str, k: int = 5, kind: str | None = None) -> list[dict]:
    """Search the RentLedger knowledge base (docs/, docs/design/, app/). Returns the top k chunks."""
    # blank query → ToolError("query must not be empty")
    # k outside 1–20 → ToolError("k must be between 1 and 20")
    # kind not in KINDS → ToolError("kind must be one of doc, design, code")
    # KnowledgeBase(KB_PATH, default_embedder()).search(...)
    # EmptyIndexError / EmbedderMismatchError / KbDependencyError → ToolError(str(exc))
    # → [{"path", "title", "kind", "text", "score"}]


if __name__ == "__main__":
    server.run("stdio")
```
`KB_PATH` is read per call, through a small `_kb_path()` helper, so tests can point it at a temp directory with `monkeypatch.setenv`.

### `.mcp.json`
```json
{"mcpServers": {"kb": {"command": ".venv/bin/python", "args": ["kb/server.py"],
                       "env": {"HF_HUB_OFFLINE": "1"}}}}
```
`HF_HUB_OFFLINE=1` stops sentence-transformers checking the Hub on every start. The model must already be cached, which happens on
the first `python kb/index.py`.

## 6. Packaging and config (`pyproject.toml`)

- `[dev]` gains `chromadb>=1.5` and `mcp>=2.3,<3` (K2). The `<3` cap is because 2.x already renamed core APIs once.
- New `[kb]` extra: `sentence-transformers>=6` (pulls in torch, and is never installed by CI).
- `[tool.setuptools.packages.find] include = ["app*", "kb*"]`.
- `addopts` gains `--cov=kb` (AC6).
- The CI workflow is unchanged: it installs `.[dev]`, which now includes chromadb and mcp.

## 7. Test plan

All tests are marked `@pytest.mark.jira("REN-6")`. Everything except the `kb_model` test uses `HashingEmbedder` and a
temp directory for `.kb`, so there's no network and no torch.

**Unit: `tests/unit/test_ren6_chunking.py`**

| AC | Test |
|----|------|
| AC2 | `test_ac2_markdown_split_by_heading_with_trail` (`# A / ## B / ### C` → titles `A`, `A › B`, `A › B › C`) |
| AC2 | `test_ac2_markdown_ignores_hash_lines_in_code_fences`; `test_ac2_markdown_preamble_titled_with_file_name`; `test_ac2_markdown_skips_empty_sections` |
| AC2 | `test_ac2_python_one_chunk_per_function_and_class` (sync, async, class with methods = 1 chunk, decorators included) |
| AC2 | `test_ac2_python_module_chunk_holds_constants_not_imports` (K3); `test_ac2_python_module_chunk_skipped_when_only_imports` |
| AC2 | `test_ac2_kind_for_paths` (design / doc / code / other → ValueError) |
| AC2 | `test_ac2_chunk_ids_stable_and_unique` (repeated heading → ordinals 0,1; same input → same ids) |
| AC2 | `test_ac2_python_syntax_error_propagates` |

**Unit: `tests/unit/test_ren6_embedding.py`**

| AC | Test |
|----|------|
| AC4 | `test_hashing_embedder_deterministic_and_normalised`; `test_hashing_embedder_similar_text_closer`; `test_hashing_embedder_empty_text_nonzero` |
| AC4 | `test_default_embedder_env_selects_hashing`; `test_missing_sentence_transformers_gives_install_hint` (blocks the import with `monkeypatch.setitem(sys.modules, "sentence_transformers", None)`) |

**Unit: `tests/unit/test_ren6_store.py`**

| AC | Test |
|----|------|
| AC1 | `test_ac1_sync_persists_to_directory` (a new `KnowledgeBase` on the same path sees the same count) |
| AC3 | `test_ac3_sync_twice_is_idempotent`; `test_ac3_changed_text_updates_in_place`; `test_ac3_removed_chunks_are_deleted` (`SyncResult.removed`) |
| AC3 | `test_ac3_embedder_change_rebuilds_collection`; `test_sync_rejects_duplicate_ids` |
| AC4 | `test_ac4_search_returns_ranked_hits_with_fields`; `test_ac4_kind_filter`; `test_ac4_k_larger_than_index` |
| AC4 | `test_ac4_search_empty_or_missing_index_raises`; `test_ac4_search_embedder_mismatch_raises_without_rebuilding` |

**Functional: `tests/functional/test_ren6_index.py`** (temp repo with `docs/design/x.md`, `docs/guide.md`, `app/a.py`, plus decoys `README.md`, `tests/t.py`, `app/notes.txt`)

| AC | Test | Asserts |
|----|------|---------|
| AC1 | `test_ac1_index_script_builds_kb_in_dot_kb` | subprocess `python kb/index.py --root <tmp>` with `RENTLEDGER_KB_EMBEDDER=hashing` → exit 0, `<tmp>/.kb` exists, output counts; decoys not indexed |
| AC1 | `test_ac1_main_in_process_reports_counts` | same through `main()`, so coverage counts it |
| AC3 | `test_ac3_reindex_no_duplicates_and_deleted_file_disappears` | 2nd run: same count, `removed 0`; delete `docs/guide.md` → 3rd run removes its chunks, `search` never returns it |
| AC1 | `test_ac1_unparseable_python_file_is_skipped_and_reported` | exit 0, file listed as skipped |
| AC1 | `test_index_without_sentence_transformers_exits_1_with_hint` | |

**Functional: `tests/functional/test_ren6_server.py`** (in-process `await server.call_tool(...)`, `RENTLEDGER_KB_PATH` → temp index)

| AC | Test | Asserts |
|----|------|---------|
| AC4 | `test_ac4_search_kb_returns_top_k_with_path_title_text` | `structured_content["result"]`: k items, keys `{path, title, kind, text, score}`, scores non-increasing |
| AC4 | `test_ac4_search_kb_default_k_is_5`; `test_ac4_search_kb_kind_filter` | |
| AC4 | `test_ac4_search_kb_rejects_bad_arguments` (parametrised: k 0 / 21, kind "x", blank query) | `ToolError` naming the argument |
| AC4 | `test_ac4_search_kb_empty_index_tells_you_to_run_indexer` | `ToolError` contains `python kb/index.py` |
| AC4 | `test_ac4_search_kb_listed_by_server` | `list_tools()` includes `search_kb` with params `query`, `k`, `kind` |

**Relevance: `tests/functional/test_ren6_relevance.py`** (K1)

| AC | Test | Asserts |
|----|------|---------|
| AC5 | `test_ac5_balance_question_finds_balance_rule_doc` (`@pytest.mark.kb_model`) | real model with `HF_HUB_OFFLINE=1`. It indexes the real repo into a temp `.kb` and asks "How is a lease balance calculated?" with k=3, expecting `docs/design/REN-5-hld.md` among the paths. **It's skipped** (with a reason) when sentence-transformers isn't installed or the model isn't cached, which is always the case in CI. |

**Repo hygiene: `tests/unit/test_ren6_repo.py`**

| AC | Test |
|----|------|
| AC6 | `test_ac6_kb_dir_is_git_ignored` (`.gitignore` has `.kb/`; `git check-ignore .kb/x` exits 0) |
| AC6 | `test_ac6_coverage_gate_includes_kb` (`addopts` contains `--cov=kb` and `--cov-fail-under=90`) |
| AC4 | `test_mcp_json_registers_kb_server` (K4) |

Order: write the tests, run them, and confirm they fail. Then implement. All earlier suites must keep passing, coverage
(now `app` + `kb`) must stay ≥ 90%, and the `kb_model` test is run locally with the result posted on REN-6.

## 8. Documentation

`README.md` gets a "Knowledge base" section:
- `pip install -e ".[kb]"`, then `python kb/index.py` (re-run after doc or code changes).
- `search_kb` is available in Claude Code through `.mcp.json`.
- `RENTLEDGER_KB_EMBEDDER=hashing` is for offline and CI use only.
