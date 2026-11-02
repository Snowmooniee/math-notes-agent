# Topology notes and finite checks

The goal is to review user-provided mathematical notes: locate a claim, examine its assumptions and reasoning, and use calculation tools where a result can be checked. The current focus is point-set topology, starting with finite spaces and continuous maps. General proof certification is outside the initial release.

## Available now: import and source lookup

The local CLI imports a text-based PDF into SQLite, searches its extracted text, and follows a result back to its source page. It also retains the original PDF so that a formula can be checked visually even if extraction loses its layout. These import and lookup commands do not call a model or judge mathematical correctness.

From a checkout with Python 3.10 or later:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev,notes]"
.\.venv\Scripts\python.exe -m math_notes import "path/to/your-notes.pdf"
.\.venv\Scripts\python.exe -m math_notes search "topology"
```

The import returns the full document `sha256`. Use that ID to read a page or recover the original file:

```powershell
$document = "paste-the-full-sha256-from-import-here"
.\.venv\Scripts\python.exe -m math_notes page $document 1
.\.venv\Scripts\python.exe -m math_notes export $document "source-for-review.pdf"
```

Commands return JSON. Errors go to stderr with exit code 1; invalid command syntax exits with code 2. Search with no matches succeeds with an empty `matches` list. The default database is `.math-notes/notes.sqlite3`, excluded from Git. Supply `--db PATH` **before** the subcommand to use another database. On Linux/macOS, use `.venv/bin/python` instead of the Windows Python path above.

## Check finite topologies and maps

```powershell
.\.venv\Scripts\python.exe -m math_notes check-topology examples/math-notes/topology-claim.json
.\.venv\Scripts\python.exe -m math_notes check-continuity examples/math-notes/continuity-claim.json
.\.venv\Scripts\python.exe -m scripts.demo_topology
```

For `check-topology`, supply `points` and `opens`. A set is a list of integer or string labels; an open-set family is a list of these sets. The result contains `valid` and a witness identifying a missing empty/full set, an element outside the space, or a failed union/intersection. The supplied example fails because the union of `{"a"}` and `{"b"}` is absent. For a finite family, binary union and intersection checks, together with the empty/full sets, suffice for the topology axioms.

For `check-continuity`, supply `domain` and `codomain` as objects with `points` and `opens`, plus `mapping` as `[source, image]` pairs, exactly one pair per domain point. The tool checks both topologies and computes every codomain open set's preimage:

- `status: "checked"` includes `continuous`, all preimages and a failed-open-set witness when false.
- `status: "undetermined"` identifies missing topologies. Omit a space's `opens` or use `null` when it is unknown; an empty list instead means an explicitly supplied, invalid family.
- `status: "invalid_topology"` identifies which supplied space fails an axiom, with its witness.

These are mathematical results and exit with code 0. A malformed input or incomplete function table exits with code 1. The CLI and the CoreCoder adapters `TopologyTool` and `ContinuityTool` share the same check functions in `math_notes.topology`.

The demo uses a two-point bijection from a discrete space to an indiscrete space. It executes both tools through CoreCoder: the forward map is continuous, but its inverse is not; the witness is the singleton `{"a"}`. Thus this continuous bijection is not a homeomorphism. `ScriptedLLM` prescribes the requests and final text: two scripted model turns, three real tool calls and zero API calls. This verifies tool integration, not model reasoning. The example is self-contained and does not require course PDFs.

## Source identity and data consistency

- A document is identified by the SHA-256 of the exact imported bytes, rather than its filename. Identical bytes under another filename return `already_present`. Changed bytes create a separate version, even if the filename is unchanged.
- The original PDF, extracted pages, extractor version, UTC import time and search index are written in one transaction. Failed writes roll back together. Concurrent writes serialize around the duplicate check, with a five-second database lock timeout.
- Citation IDs have the form `sha256:<document hash>#page=<PDF page>`. PDF pages are counted from 1, including pages with no text. Printed page numbers remain `null` until a separate mapping has been checked.
- The raw extraction is kept without fixing mathematical notation automatically. `page` returns the full extracted page; `export` checks the stored source hash and refuses to overwrite an existing file.
- Readers open the database in read-only mode. An application identifier and schema version identify the supported database format. There is no automatic schema migration yet.

## Retrieval baseline

SQLite FTS5 indexes one page per source unit. Search treats input as literal keywords: all terms must match, and results are ordered by BM25 with a stable tie-break. SQL values are parameterized; query text cannot supply SQL or FTS operators. Use `search QUERY --document HASH --limit N` to narrow results; the limit is 1-20.

This is an English keyword baseline. It does not provide semantic search, cross-language retrieval, Chinese word segmentation, or natural-language answers. A matching passage is a source locator, not evidence that its contents are correct. Future retrieval changes should be compared against this baseline on fixed questions.

## Input limits and known failures

Imports accept PDFs up to 20 MiB and 200 pages, with an 8 MiB decoded content-stream limit per page and a 2,000,000-character total extraction limit. Encrypted files and documents with no extractable text are rejected. Mixed documents retain empty pages and report their numbers.

Scans, handwriting, automatic printed-page mapping and reliable reconstruction of mathematical notation are not supported. Check extracted sets, mappings and formulas against the retained PDF. See the [pypdf extraction limitations](https://pypdf.readthedocs.io/en/stable/user/extract-text.html) and [SQLite FTS5 documentation](https://www.sqlite.org/fts5.html).

## Verification

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_math_notes.py -q
.\.venv\Scripts\python.exe -m pytest tests/test_topology.py -q
```

The tests cover PDF/SQLite behavior and the mathematical tools. The topology suite also compares the binary-operation algorithm with the full union/intersection definition across all open-set candidates containing the empty/full sets on a three-point space. Synthetic inputs and scripted traces test software behavior, not model review accuracy. Course notes are not distributed in this repository.

## Next

Connect source lookup and the calculation tool to one model-driven review. A review should show the claim, assumptions, supporting sources, tool results, and unresolved questions. Define and review the task cases before measuring quality; see the [evaluation criteria and comparison plan](review-evaluation.md). Model behavior, costs and review quality still require real evaluation. A web interface is deferred until this workflow is demonstrated.

The CoreCoder engine is unchanged. Its [local upstream baseline](upstream-baseline.md), original Git history and [MIT license](../LICENSE) are retained.
