"""Local PDF ingestion and source lookup for Math Notes Agent."""

import hashlib
import re
import sqlite3
from contextlib import contextmanager
from io import BytesIO
from pathlib import Path

import pypdf

MAX_FILE_BYTES = 20 * 1024 * 1024
MAX_PAGES = 200
MAX_PAGE_STREAM_BYTES = 8 * 1024 * 1024
MAX_TEXT_CHARS = 2_000_000
APPLICATION_ID = 0x4D4E4F54  # MNOT
SCHEMA_VERSION = 1

_SCHEMA = (
    """CREATE TABLE documents (
        sha256 TEXT PRIMARY KEY NOT NULL,
        file_name TEXT NOT NULL,
        byte_count INTEGER NOT NULL,
        page_count INTEGER NOT NULL,
        extractor TEXT NOT NULL,
        pdf_bytes BLOB NOT NULL,
        imported_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )""",
    """CREATE TABLE pages (
        id INTEGER PRIMARY KEY,
        document_sha256 TEXT NOT NULL REFERENCES documents(sha256),
        pdf_page INTEGER NOT NULL CHECK (pdf_page > 0),
        printed_page TEXT,
        text TEXT NOT NULL,
        UNIQUE (document_sha256, pdf_page)
    )""",
    "CREATE VIRTUAL TABLE pages_fts USING fts5(text, content='pages', content_rowid='id')",
)


@contextmanager
def _store(db_path: str | Path, *, writable: bool = False):
    path = Path(db_path).expanduser().resolve()
    if writable:
        path.parent.mkdir(parents=True, exist_ok=True)
    mode = "rwc" if writable else "ro"
    connection = sqlite3.connect(f"{path.as_uri()}?mode={mode}", uri=True, timeout=5)
    connection.row_factory = sqlite3.Row
    try:
        connection.execute("PRAGMA foreign_keys = ON")
        with connection:
            if writable:
                # Serialize the duplicate check and insert, including simultaneous imports.
                connection.execute("BEGIN IMMEDIATE")
            app_id = connection.execute("PRAGMA application_id").fetchone()[0]
            version = connection.execute("PRAGMA user_version").fetchone()[0]
            empty = connection.execute("SELECT 1 FROM sqlite_master LIMIT 1").fetchone() is None
            if writable and app_id == 0 and version == 0 and empty:
                for statement in _SCHEMA:
                    connection.execute(statement)
                connection.execute(f"PRAGMA application_id = {APPLICATION_ID}")
                connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
            elif (app_id, version) != (APPLICATION_ID, SCHEMA_VERSION):
                raise ValueError("Not a supported Math Notes database; use a new database path.")
            yield connection
    finally:
        connection.close()


def _validate_sha256(value: str) -> str:
    if not isinstance(value, str) or re.fullmatch(r"[0-9a-fA-F]{64}", value) is None:
        raise ValueError("Document ID must be a full SHA-256 hash.")
    return value.lower()


def _summary(connection, sha256: str, *, status: str) -> dict:
    document = dict(
        connection.execute(
            "SELECT sha256, file_name, byte_count, page_count, extractor, imported_at FROM documents WHERE sha256 = ?",
            (sha256,),
        ).fetchone()
    )
    empty_pages = [
        row["pdf_page"]
        for row in connection.execute("SELECT pdf_page, text FROM pages WHERE document_sha256 = ? ORDER BY pdf_page", (sha256,))
        if not row["text"].strip()
    ]
    return {"status": status, **document, "empty_pages": empty_pages}


def import_pdf(pdf_path: str | Path, db_path: str | Path) -> dict:
    """Extract one immutable PDF snapshot, then atomically store all its pages."""
    path = Path(pdf_path).expanduser()
    if path.suffix.lower() != ".pdf":
        raise ValueError("Only text-based PDF files are supported.")
    with path.open("rb") as source:
        data = source.read(MAX_FILE_BYTES + 1)
    if len(data) > MAX_FILE_BYTES:
        raise ValueError(f"PDF exceeds the {MAX_FILE_BYTES}-byte input limit.")
    if b"%PDF-" not in data[:1024]:
        raise ValueError("File does not have a PDF header.")

    # Hash and parse the same bytes, even if the source file changes during import.
    sha256 = hashlib.sha256(data).hexdigest()
    reader = pypdf.PdfReader(BytesIO(data))
    if reader.is_encrypted:
        raise ValueError("Encrypted PDFs are not supported; provide an unencrypted copy.")
    if not 1 <= len(reader.pages) <= MAX_PAGES:
        raise ValueError(f"PDF must contain between 1 and {MAX_PAGES} pages.")

    texts = []
    text_chars = 0
    for page in reader.pages:
        contents = page.get_contents()
        if contents is not None and len(contents.get_data()) > MAX_PAGE_STREAM_BYTES:
            raise ValueError("PDF page exceeds the decoded content-stream limit.")
        text = page.extract_text() or ""
        text_chars += len(text)
        if text_chars > MAX_TEXT_CHARS:
            raise ValueError(f"PDF exceeds the {MAX_TEXT_CHARS}-character extracted-text limit.")
        texts.append(text)
    if not any(text.strip() for text in texts):
        raise ValueError("PDF has no extractable text. Scanned notes require OCR, which is not supported.")

    with _store(db_path, writable=True) as connection:
        if connection.execute("SELECT 1 FROM documents WHERE sha256 = ?", (sha256,)).fetchone():
            return _summary(connection, sha256, status="already_present")
        connection.execute(
            "INSERT INTO documents (sha256, file_name, byte_count, page_count, extractor, pdf_bytes) VALUES (?, ?, ?, ?, ?, ?)",
            (sha256, path.name, len(data), len(texts), f"pypdf/{pypdf.__version__}:plain", data),
        )
        for number, text in enumerate(texts, start=1):
            cursor = connection.execute(
                "INSERT INTO pages (document_sha256, pdf_page, text) VALUES (?, ?, ?)", (sha256, number, text)
            )
            # Source rows and their index entries share the same transaction.
            connection.execute("INSERT INTO pages_fts (rowid, text) VALUES (?, ?)", (cursor.lastrowid, text))
        return _summary(connection, sha256, status="imported")


def _source(row) -> dict:
    result = dict(row)
    result["citation"] = f"sha256:{result['document_sha256']}#page={result['pdf_page']}"
    return result


def search_notes(db_path: str | Path, query: str, *, document: str | None = None, limit: int = 5) -> list[dict]:
    """Find pages containing all literal query terms. This is lexical retrieval, not verification."""
    if not isinstance(query, str) or not 1 <= len(query) <= 500:
        raise ValueError("Query must contain between 1 and 500 characters.")
    if type(limit) is not int or not 1 <= limit <= 20:
        raise ValueError("Limit must be an integer between 1 and 20.")
    terms = re.findall(r"[^\W_]+", query, flags=re.UNICODE)
    if not terms or len(terms) > 32:
        raise ValueError("Query must contain between 1 and 32 searchable terms.")
    if document is not None:
        document = _validate_sha256(document)
    # Treat operators and punctuation as user text, never as FTS/SQL syntax.
    match = " AND ".join(f'"{term}"' for term in terms)
    with _store(db_path) as connection:
        rows = connection.execute(
            """SELECT p.document_sha256, d.file_name, p.pdf_page, p.printed_page,
                      snippet(pages_fts, 0, '[', ']', ' ... ', 32) AS excerpt
               FROM pages_fts
               JOIN pages p ON p.id = pages_fts.rowid
               JOIN documents d ON d.sha256 = p.document_sha256
               WHERE pages_fts MATCH ? AND (? IS NULL OR p.document_sha256 = ?)
               ORDER BY bm25(pages_fts), p.document_sha256, p.pdf_page
               LIMIT ?""",
            (match, document, document, limit),
        ).fetchall()
    return [_source(row) for row in rows]


def get_page(db_path: str | Path, document: str, pdf_page: int) -> dict:
    """Return the complete extracted text behind a citation, without altering the database."""
    document = _validate_sha256(document)
    if type(pdf_page) is not int or pdf_page < 1:
        raise ValueError("PDF page must be a positive integer, counted from 1.")
    with _store(db_path) as connection:
        row = connection.execute(
            """SELECT p.document_sha256, d.file_name, d.extractor,
                      p.pdf_page, p.printed_page, p.text
               FROM pages p JOIN documents d ON d.sha256 = p.document_sha256
               WHERE p.document_sha256 = ? AND p.pdf_page = ?""",
            (document, pdf_page),
        ).fetchone()
    if row is None:
        raise ValueError("Document or PDF page was not found.")
    return _source(row)


def export_pdf(db_path: str | Path, document: str, output: str | Path) -> dict:
    """Recover the exact source PDF for visual review, refusing to overwrite files."""
    document = _validate_sha256(document)
    with _store(db_path) as connection:
        row = connection.execute("SELECT pdf_bytes FROM documents WHERE sha256 = ?", (document,)).fetchone()
    if row is None:
        raise ValueError("Document was not found.")
    if hashlib.sha256(row["pdf_bytes"]).hexdigest() != document:
        raise ValueError("Stored PDF does not match its SHA-256; do not use it as a source.")
    path = Path(output).expanduser()
    with path.open("xb") as destination:
        destination.write(row["pdf_bytes"])
    return {"status": "exported", "sha256": document, "file_name": path.name}
