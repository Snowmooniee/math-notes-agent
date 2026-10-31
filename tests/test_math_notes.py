"""Exercise real PDF extraction and SQLite transactions; no model responses are involved."""

import hashlib
import json
import shutil
import sqlite3
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

import pytest
from pypdf import PdfWriter
from pypdf.errors import PyPdfError
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

import math_notes
from math_notes import export_pdf, get_page, import_pdf, search_notes
from math_notes.__main__ import main


@pytest.fixture
def pdf_factory(tmp_path):
    """Create small text PDFs directly, without a document-generation dependency."""

    def make(pages, *, name="notes.pdf", password=None):
        writer = PdfWriter()
        for text in pages:
            page = writer.add_blank_page(width=612, height=792)
            font = DictionaryObject(
                {
                    NameObject("/Type"): NameObject("/Font"),
                    NameObject("/Subtype"): NameObject("/Type1"),
                    NameObject("/BaseFont"): NameObject("/Helvetica"),
                }
            )
            page[NameObject("/Resources")] = DictionaryObject(
                {
                    NameObject("/Font"): DictionaryObject({NameObject("/F1"): font}),
                }
            )
            lines = []
            for line in text.splitlines():
                escaped = line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
                lines.append(f"({escaped}) Tj T*")
            stream = DecodedStreamObject()
            stream.set_data(("BT /F1 12 Tf 16 TL 40 740 Td\n" + "\n".join(lines) + "\nET").encode("ascii"))
            page[NameObject("/Contents")] = stream
        if password:
            writer.encrypt(password)
        path = tmp_path / name
        writer.write(path)
        return path

    return make


@pytest.fixture
def notes_pdf(pdf_factory):
    return pdf_factory(
        [
            "Nullspace\nThe nullspace of A consists of the vectors v satisfying A v = 0.\nPrinted page 41",
            "",
            "Rank and nullity\nFor an m by n matrix A, rank(A) + nullity(A) = n.\nPrinted page 43",
        ]
    )


def test_import_search_and_follow_source(notes_pdf, tmp_path):
    database = tmp_path / "local data" / "notes.sqlite3"
    original = notes_pdf.read_bytes()
    result = import_pdf(notes_pdf, database)
    assert result["status"] == "imported"
    assert result["sha256"] == hashlib.sha256(original).hexdigest()
    assert result["page_count"] == 3 and result["empty_pages"] == [2]
    assert result["file_name"] == "notes.pdf" and result["extractor"].startswith("pypdf/")
    assert notes_pdf.read_bytes() == original

    matches = search_notes(database, "RANK nullity")
    assert len(matches) == 1 and matches[0]["pdf_page"] == 3
    assert matches[0]["printed_page"] is None  # Printed numbers are not inferred from PDF position.
    assert matches[0]["citation"] == f"sha256:{result['sha256']}#page=3"
    source = get_page(database, result["sha256"], 3)
    assert "rank(A) + nullity(A) = n" in source["text"]
    assert source["citation"] == matches[0]["citation"]
    assert not get_page(database, result["sha256"], 2)["text"].strip()
    assert search_notes(database, "quantum entanglement") == []


def test_duplicate_bytes_different_name_do_not_duplicate_pages(notes_pdf, tmp_path):
    database = tmp_path / "notes.sqlite3"
    first = import_pdf(notes_pdf, database)
    renamed = tmp_path / "renamed.pdf"
    shutil.copyfile(notes_pdf, renamed)
    second = import_pdf(renamed, database)
    assert second == {**first, "status": "already_present"}
    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT COUNT(*) FROM documents").fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM pages").fetchone()[0] == 3
    assert len(search_notes(database, "nullspace")) == 1


def test_simultaneous_imports_are_idempotent(notes_pdf, tmp_path):
    database = tmp_path / "notes.sqlite3"
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: import_pdf(notes_pdf, database), range(2)))
    assert sorted(result["status"] for result in results) == ["already_present", "imported"]
    assert len(search_notes(database, "nullspace")) == 1


def test_changed_bytes_are_a_new_revision_and_search_can_be_scoped(notes_pdf, pdf_factory, tmp_path):
    database = tmp_path / "notes.sqlite3"
    old = import_pdf(notes_pdf, database)
    pdf_factory(["Nullspace revision: check the vector by substitution."], name="notes.pdf")
    new = import_pdf(notes_pdf, database)
    assert new["sha256"] != old["sha256"]
    assert len(search_notes(database, "nullspace")) == 2
    matches = search_notes(database, "nullspace", document=old["sha256"])
    assert len(matches) == 1 and matches[0]["document_sha256"] == old["sha256"]
    assert len(search_notes(database, "nullspace", limit=1)) == 1


def test_original_pdf_can_be_recovered_after_source_changes(notes_pdf, tmp_path):
    database = tmp_path / "notes.sqlite3"
    original = notes_pdf.read_bytes()
    document = import_pdf(notes_pdf, database)["sha256"]
    notes_pdf.write_bytes(b"source replaced after import")
    recovered = tmp_path / "recovered.pdf"
    assert export_pdf(database, document, recovered)["status"] == "exported"
    assert recovered.read_bytes() == original
    with pytest.raises(FileExistsError):
        export_pdf(database, document, notes_pdf)
    assert notes_pdf.read_bytes() == b"source replaced after import"


def test_export_detects_corrupt_source_bytes(notes_pdf, tmp_path):
    database = tmp_path / "notes.sqlite3"
    document = import_pdf(notes_pdf, database)["sha256"]
    with sqlite3.connect(database) as connection:
        connection.execute("UPDATE documents SET pdf_bytes = ? WHERE sha256 = ?", (b"corrupt", document))
    recovered = tmp_path / "recovered.pdf"
    with pytest.raises(ValueError, match="does not match its SHA-256"):
        export_pdf(database, document, recovered)
    assert not recovered.exists()


def test_failed_insert_rolls_back_pages_document_and_index(notes_pdf, pdf_factory, tmp_path):
    database = tmp_path / "notes.sqlite3"
    original = import_pdf(notes_pdf, database)
    with sqlite3.connect(database) as connection:
        connection.execute("""CREATE TRIGGER fail_second_page BEFORE INSERT ON pages
            WHEN NEW.pdf_page = 2 BEGIN SELECT RAISE(ABORT, 'injected write failure'); END""")
    broken = pdf_factory(["Rollbackneedle first page", "Rollbackneedle second page"], name="other.pdf")
    with pytest.raises(sqlite3.IntegrityError, match="injected write failure"):
        import_pdf(broken, database)
    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT COUNT(*) FROM documents").fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM pages").fetchone()[0] == 3
    assert search_notes(database, "rollbackneedle") == []
    assert get_page(database, original["sha256"], 1)["text"].startswith("Nullspace")


@pytest.mark.parametrize("data", [b"not a pdf", b"%PDF-1.7\nbroken body"])
def test_invalid_pdf_does_not_create_a_database(data, tmp_path):
    source, database = tmp_path / "broken.pdf", tmp_path / "absent.sqlite3"
    source.write_bytes(data)
    with pytest.raises((ValueError, PyPdfError)):
        import_pdf(source, database)
    assert not database.exists()


def test_encrypted_and_textless_pdfs_are_rejected(pdf_factory, tmp_path):
    database = tmp_path / "absent.sqlite3"
    for source, message in [
        (pdf_factory(["Private"], name="encrypted.pdf", password="secret"), "Encrypted"),
        (pdf_factory(["", ""], name="blank.pdf"), "no extractable text"),
    ]:
        with pytest.raises(ValueError, match=message):
            import_pdf(source, database)
        assert not database.exists()


@pytest.mark.parametrize(
    "setting, value, message",
    [
        ("MAX_FILE_BYTES", 32, "input limit"),
        ("MAX_PAGES", 2, "between 1 and 2 pages"),
        ("MAX_PAGE_STREAM_BYTES", 16, "content-stream limit"),
        ("MAX_TEXT_CHARS", 16, "extracted-text limit"),
    ],
)
def test_input_limits_do_not_leave_partial_imports(setting, value, message, notes_pdf, tmp_path, monkeypatch):
    monkeypatch.setattr(math_notes, setting, value)
    database = tmp_path / "absent.sqlite3"
    with pytest.raises(ValueError, match=message):
        import_pdf(notes_pdf, database)
    assert not database.exists()


@pytest.mark.parametrize("query", ["", "!!!", "x" * 501, "word " * 33])
def test_invalid_queries_fail_before_opening_database(query, tmp_path):
    with pytest.raises(ValueError, match="Query"):
        search_notes(tmp_path / "absent.sqlite3", query)


def test_user_query_cannot_inject_sql_or_fts_operators(notes_pdf, tmp_path):
    database = tmp_path / "notes.sqlite3"
    import_pdf(notes_pdf, database)
    assert search_notes(database, 'nullspace" OR "rank') == []
    assert search_notes(database, "' OR 1=1; DROP TABLE documents;--") == []
    assert len(search_notes(database, "nullspace")) == 1
    assert search_notes(database, "Nullspace?!")[0]["pdf_page"] == 1


@pytest.mark.parametrize("limit", [0, 21, True, 1.5])
def test_invalid_result_limits(limit, tmp_path):
    with pytest.raises(ValueError, match="Limit"):
        search_notes(tmp_path / "absent.sqlite3", "nullspace", limit=limit)


def test_reading_missing_store_does_not_create_it(tmp_path):
    database = tmp_path / "absent.sqlite3"
    with pytest.raises(sqlite3.OperationalError):
        search_notes(database, "nullspace")
    assert not database.exists()


def test_unicode_and_uri_special_characters_in_paths(pdf_factory, tmp_path):
    source = pdf_factory(["Nullspace source"], name="\u7b14\u8bb0 #1's notes.PDF")
    database = tmp_path / "local #1's \u7b14\u8bb0.sqlite3"
    result = import_pdf(source, database)
    assert result["file_name"] == source.name
    assert search_notes(database, "nullspace")[0]["file_name"] == source.name


def test_missing_wrong_format_and_zero_page_inputs(pdf_factory, tmp_path):
    database = tmp_path / "absent.sqlite3"
    with pytest.raises(FileNotFoundError):
        import_pdf(tmp_path / "absent.pdf", database)
    with pytest.raises(ValueError, match="Only text-based PDF"):
        import_pdf(tmp_path / "notes.txt", database)
    with pytest.raises(ValueError, match="between 1 and"):
        import_pdf(pdf_factory([]), database)
    assert not database.exists()


def test_unknown_schema_and_unrelated_database_are_not_modified(notes_pdf, tmp_path):
    database = tmp_path / "notes.sqlite3"
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE unrelated (value TEXT)")
        connection.execute("INSERT INTO unrelated VALUES ('keep me')")
    with pytest.raises(ValueError, match="supported Math Notes database"):
        import_pdf(notes_pdf, database)
    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT value FROM unrelated").fetchone()[0] == "keep me"
        connection.execute("DROP TABLE unrelated")
    result = import_pdf(notes_pdf, database)
    with sqlite3.connect(database) as connection:
        connection.execute("PRAGMA user_version = 999")
    with pytest.raises(ValueError, match="supported Math Notes database"):
        get_page(database, result["sha256"], 1)


def test_unknown_document_and_page_are_explicit_errors(notes_pdf, tmp_path):
    database = tmp_path / "notes.sqlite3"
    result = import_pdf(notes_pdf, database)
    with pytest.raises(ValueError, match="SHA-256"):
        get_page(database, "invalid", 1)
    with pytest.raises(ValueError, match="positive integer"):
        get_page(database, result["sha256"], 0)
    with pytest.raises(ValueError, match="not found"):
        get_page(database, result["sha256"], 4)
    with pytest.raises(ValueError, match="not found"):
        get_page(database, "0" * 64, 1)


def test_cli_json_and_error_exit_status(notes_pdf, tmp_path, capsys):
    args = ["--db", str(tmp_path / "notes.sqlite3")]
    assert main([*args, "import", str(notes_pdf)]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "imported"
    assert main([*args, "search", "nullspace"]) == 0
    match = json.loads(capsys.readouterr().out)["matches"][0]
    assert main([*args, "page", match["document_sha256"], "1"]) == 0
    assert "A v = 0" in json.loads(capsys.readouterr().out)["text"]
    assert main([*args, "page", match["document_sha256"], "99"]) == 1
    captured = capsys.readouterr()
    assert not captured.out and "not found" in json.loads(captured.err)["error"]


def test_module_entrypoint_without_model_keys(notes_pdf, tmp_path, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    result = subprocess.run(
        [sys.executable, "-m", "math_notes", "--db", str(tmp_path / "notes.sqlite3"), "import", str(notes_pdf)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["status"] == "imported"
