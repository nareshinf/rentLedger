# REN-6 — Knowledge base and search_kb tool: High-Level Design

- **Issue:** [REN-6](https://nareshmalhotra.atlassian.net/browse/REN-6) (parent epic REN-1)
- **Stage:** HLD (awaiting `hld-approved`)
- **Branch:** `REN-6-knowledge-base`, stacked on `REN-5-payments-balance` (PR #4 open). It's stacked
  because AC5 needs `docs/design/REN-5-hld.md`, which documents the balance rule.

## 1. Goal

Build a local semantic index of the project's docs and code, and expose it to Claude through an MCP
tool `search_kb`. CLAUDE.md's "run `search_kb` before designing" step then becomes possible.

## 2. Scope

| AC | Outcome |
|----|---------|
| AC1 | `python kb/index.py` indexes `docs/**/*.md` and `app/**/*.py` into a vector store in `.kb/` |
| AC2 | Markdown chunked by heading; Python one function/class per chunk; each chunk has path, heading/symbol, kind |
| AC3 | Re-indexing is idempotent: no duplicates, and deleted files drop out |
| AC4 | MCP tool `search_kb(query, k=5, kind=None)` → top k chunks with path, heading/symbol, text |
| AC5 | "How is a lease balance calculated?" → the file documenting the balance rule is in the top 3 |
| AC6 | `.kb/` git-ignored; unit + functional tests; coverage gate includes `kb/` |

**Out of scope:** indexing `README.md`, `CLAUDE.md` or `tests/` (the AC fixes the globs), automatic
re-indexing on file change or in CI, hybrid/keyword search, and the `.claude/skills/` from CLAUDE.md's layout.

## 3. Context

- The stack named in CLAUDE.md is **ChromaDB + sentence-transformers**, exposed through the `kb` MCP server.
  The `mcp` Python SDK isn't named, but an MCP server needs it, so it's listed as a new library in §6.
- Current corpus: 8 design docs (REN-2 to REN-5 HLD and LLD) and about 20 small Python modules in `app/`, giving
  a few hundred chunks. Re-embedding everything takes seconds on a laptop CPU.
- `all-MiniLM-L6-v2` (384 dimensions, about 90 MB) is already in the local Hugging Face cache.
- CLAUDE.md test rule: **no real network in tests**.

## 4. Design

### 4.1 Components (`kb/`)

```
kb/chunking.py   pure functions: markdown_chunks(path, text), python_chunks(path, text) → list[Chunk]
kb/store.py      KnowledgeBase(path, embedder): sync(chunks) and search(query, k, kind) over a Chroma collection
kb/embedding.py  Embedder protocol; SentenceTransformerEmbedder (real, lazy import); HashingEmbedder (tests)
kb/index.py      CLI: collect files → chunk → KnowledgeBase(".kb").sync(); prints counts
kb/server.py     MCP stdio server (FastMCP) with one tool, search_kb
.mcp.json        registers the `kb` server for Claude Code in this repo
```
`Chunk = {id, path, title, kind, text}`. `title` holds the heading path or the symbol, which is the AC's "heading or symbol".

### 4.2 Chunking (AC2)

- **Markdown:** split on ATX headings (`#`…`######`), ignoring `#` lines inside fenced code blocks.
  - Each chunk's `title` is the heading trail, for example `REN-5 … HLD › 4. Design › 4.3 Balance calculation`. The parent headings give the embedding context.
  - Text before the first heading becomes a chunk titled with the file name. Empty sections are skipped.
- **Python:** `ast` walks the module and makes one chunk per **top-level** `def`, `async def` and `class`. A class
  chunk includes its methods. `title` = the symbol name (`compute_balance`, `LeaseCreate`), and the text is the exact source
  segment, including decorators and docstring.
  - Per **K3**, each file also gets one `<module>` chunk holding the module docstring and top-level statements other than
    imports, such as constants and type aliases like `Money`.
- **Kind:** `docs/design/**` → `design`; other `docs/**` → `doc`; `app/**` → `code`.

### 4.3 Store and idempotency (AC1, AC3)

- Chroma `PersistentClient(path=".kb")` with one collection, `rentledger`, using cosine distance.
  Embeddings are computed by our `Embedder` and passed in explicitly, so Chroma never calls its own default model.
- **Chunk id** = `sha1(path + title + ordinal)`. The ordinal disambiguates repeated headings in one file.
- **`sync(chunks)`:**
  1. Upsert every current chunk, so changed text replaces the old entry under the same id.
  2. Delete every id in the collection that isn't in the current set.

  Running it twice gives the same collection, and a deleted file's chunks drop out in step 2.
- The collection metadata records the embedder name. If it changes, the collection is rebuilt, so vectors from different
  models are never mixed.

### 4.4 `search_kb` (AC4)

```
search_kb(query: str, k: int = 5, kind: str | None = None)
  → [{"path", "title", "kind", "text", "score"}, …]      # ordered best first
```
- `k` is 1–20, and `kind` is one of `doc` / `design` / `code` / `None`. Invalid values give an MCP tool error naming the argument.
- If the index is missing or empty, it raises a tool error saying "Knowledge base is empty — run `python kb/index.py`".
- `score` = 1 − cosine distance, rounded to 3 decimal places.
- The server only reads: it opens `.kb/` per call, so re-indexing while Claude Code is running is picked up.

### 4.5 Repository wiring (AC6)

- `.gitignore` gets `.kb/`.
- `pyproject.toml`:
  - `--cov=kb` is added alongside `--cov=app`, so the 90% gate covers `kb/`.
  - The package `include` gets `kb*`.
- **Running `python kb/index.py` as a script:** Python puts `kb/` on `sys.path`, not the repo root. The script entry
  therefore does a small root-path bootstrap before `from kb… import …`. The LLD will pin this down.

## 5. Testing strategy

Every test is marked `@pytest.mark.jira("REN-6")`.

| AC | Unit | Functional |
|----|------|-----------|
| AC1 | file collection honours the two globs and skips everything else | run `kb/index.py` main in a temp repo copy → `.kb/` created, counts printed |
| AC2 | markdown: headings, nested trail, fenced `#`, preamble, empty sections; python: functions, async, classes with methods, decorators; kind mapping | — |
| AC3 | `sync` twice → same ids/count; edit a section → updated text, same count; delete a file → its chunks gone | index temp repo, delete a doc, re-index → absent from `search_kb` |
| AC4 | argument validation; empty-index error; result shape and order | call the FastMCP tool in-process: shape, `k`, `kind` filter |
| AC5 | — | see decision **K1** |
| AC6 | — | a test asserts `.gitignore` contains `.kb/` and pyproject `addopts` contains `--cov=kb` |

## 6. New libraries

| Library | Why |
|---------|-----|
| `chromadb` | Named in CLAUDE.md, for the local persistent vector store |
| `sentence-transformers` (pulls in `torch`) | Named in CLAUDE.md, for embeddings with `all-MiniLM-L6-v2` |
| `mcp` | **Not named in CLAUDE.md.** It's the official Python SDK, needed to serve `search_kb` over MCP |

A dry run resolved all of them on Python 3.12: chromadb 1.5.9, mcp 2.3.0 and sentence-transformers 6.2.0, adding 87 packages including torch.

## 7. Decisions (recommendations accepted in review)

| # | Question | **Decision** |
|---|----------|----------------|
| **K1** | How can AC5 be tested without breaking "no real network in tests"? The real model must be downloaded once. | **Two tiers.** CI and default `pytest` use a deterministic `HashingEmbedder` (no network, no torch) for all AC1–AC4/AC6 tests. AC5 is a test marked `kb_model` that uses the real model **only if it's already cached locally** (`HF_HUB_OFFLINE=1`), and is otherwise skipped with a clear reason. I run it locally and post the evidence. Faking AC5 with a toy embedder would prove nothing about relevance. |
| **K2** | Dependency weight: torch is very large, so it would slow every CI run. | **Split extras.** `[dev]` gains `chromadb` and `mcp`, which CI needs for the KB tests. A new `[kb]` extra holds `sentence-transformers`, installed only by people who build a real index. CI never installs torch. The real embedder imports it lazily, and those few lines are covered by the `kb_model` test (excluded from the CI coverage run with a narrow `pragma: no cover` if needed). |
| **K3** | Python module-level code (constants, type aliases like `Money`, `DueDay`) isn't in any function or class. | **Add one `<module>` chunk per file** holding the module docstring and top-level statements other than imports. Without it, the money and due-day rules in `schemas.py` can't be found. This goes slightly beyond AC2's "one function or class per chunk", so it needs your OK. |
| **K4** | Register the MCP server in a committed `.mcp.json`? | **Yes**, so anyone opening the repo in Claude Code gets `search_kb` after running the indexer. It runs locally over stdio and makes no network calls. |

## 8. Risks

- **Install size:** `[kb]` brings in torch, which is mitigated by K2. Chroma also pulls in `onnxruntime`. Our explicit embeddings mean
  Chroma's own default model is never downloaded.
- **AC5 depends on the doc content.** It passes because `REN-5-hld.md` §4.3 documents the formula. If that doc
  moves, the test points at the new location.
- **Stacked branch:** REN-6's PR targets `main` after PR #4 merges.
