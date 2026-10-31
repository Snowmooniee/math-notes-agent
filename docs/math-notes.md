# Math Notes Agent

The goal is to review user-provided mathematical notes: locate a claim, examine its assumptions and reasoning, and use calculation tools where a result can be checked. The first examples will use linear algebra. General proof certification is outside the initial release.

## Available now: import and source lookup

The local CLI imports a text-based PDF into SQLite, searches its extracted text, and follows a result back to its source page. It also retains the original PDF so that a formula can be checked visually even if extraction loses its layout. These commands do not call a model or judge mathematical correctness.

From a checkout with Python 3.10 or later:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev,notes]"
.\.venv\Scripts\python.exe -m math_notes import "path/to/your-notes.pdf"
.\.venv\Scripts\python.exe -m math_notes search "nullspace"
```

The import returns the full document `sha256`. Use that ID to read a page or recover the original file:

```powershell
$document = "paste-the-full-sha256-from-import-here"
.\.venv\Scripts\python.exe -m math_notes page $document 12
.\.venv\Scripts\python.exe -m math_notes export $document "source-for-review.pdf"
```

Commands return JSON. Errors go to stderr with exit code 1; invalid command syntax exits with code 2. Search with no matches succeeds with an empty `matches` list. The default database is `.math-notes/notes.sqlite3`, excluded from Git. Supply `--db PATH` **before** the subcommand to use another database. On Linux/macOS, use `.venv/bin/python` instead of the Windows Python path above.

## Source identity and data consistency

- A document is identified by the SHA-256 of the exact imported bytes, rather than its filename. Identical bytes under another filename return `already_present`. Changed bytes create a separate version, even if the filename is unchanged.
- The original PDF, extracted pages, extractor version, UTC import time and search index are written in one transaction. Failed writes roll back together. Concurrent writes serialize around the duplicate check, with a five-second database lock timeout.
- Citation IDs have the form `sha256:<document hash>#page=<PDF page>`. PDF pages are counted from 1, including pages with no text. Printed page numbers remain `null` until a separate mapping has been checked.
- The raw extraction is kept without fixing mathematical notation automatically. `page` returns the full extracted page; `export` checks the stored source hash and refuses to overwrite an existing file.
- Readers open the database in read-only mode. An application identifier and schema version prevent adopting an unrelated or newer database. There is no automatic schema migration yet; keep a backup before future upgrades.

## Retrieval baseline

SQLite FTS5 indexes one page per source unit. Search treats input as literal keywords: all terms must match, and results are ordered by BM25 with a stable tie-break. SQL values are parameterized; query text cannot supply SQL or FTS operators. Use `search QUERY --document HASH --limit N` to narrow results; the limit is 1-20.

This is an English keyword baseline. It does not provide semantic search, cross-language retrieval, Chinese word segmentation, or natural-language answers. A matching passage is a source locator, not evidence that its contents are correct. Future retrieval changes should be compared against this baseline on fixed questions.

## Input limits and known failures

Imports accept PDFs up to 20 MiB and 200 pages, with an 8 MiB decoded content-stream limit per page and a 2,000,000-character total extraction limit. Encrypted files and documents with no extractable text are rejected. Mixed documents retain empty pages and report their numbers.

These limits bound accepted input and stored text, but PDF parsing/decompression happens before some checks. This local CLI is not a sandbox for hostile uploads; a public upload service needs parser process isolation and resource limits. Scans, handwriting, automatic printed-page mapping and reliable reconstruction of matrices or fractions are not supported. Extraction quality must be checked against the retained PDF. See the [pypdf extraction limitations](https://pypdf.readthedocs.io/en/stable/user/extract-text.html) and [SQLite FTS5 documentation](https://www.sqlite.org/fts5.html).

## Verification

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_math_notes.py -q
```

The tests generate small text PDFs using pypdf. They exercise extraction, source lookup, original-file recovery, duplicate and concurrent imports, changed document versions, injected write failures, malformed/encrypted/textless files, input limits, query handling, and command-line exit status. The synthetic notes test software behavior, not mathematical review accuracy. Course notes are not distributed in this repository.

## Next

Add a restricted matrix calculation and verification tool, then connect source lookup and calculation to the CoreCoder tool loop. A review should show the claim, assumptions, supporting sources, tool results, and unresolved questions. A simple Django interface and saved review history will follow. Model behavior, costs and review quality still require real evaluation.

The CoreCoder engine is unchanged. Its [local upstream baseline](upstream-baseline.md), original Git history and [MIT license](../LICENSE) are retained.
