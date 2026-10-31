"""Command-line entry point; JSON output is suitable for scripts and later tool adapters."""

import argparse
import json
import sqlite3
import sys

from pypdf.errors import PyPdfError

from . import export_pdf, get_page, import_pdf, search_notes


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Import PDF notes and look up their source pages.")
    parser.add_argument("--db", default=".math-notes/notes.sqlite3", help="Local Math Notes database path")
    commands = parser.add_subparsers(dest="command", required=True)
    ingest = commands.add_parser("import", help="Import a text-based PDF")
    ingest.add_argument("pdf")
    search = commands.add_parser("search", help="Search literal keywords; all query terms must match")
    search.add_argument("query")
    search.add_argument("--document", help="Restrict results to a full document SHA-256")
    search.add_argument("--limit", type=int, default=5)
    page = commands.add_parser("page", help="Read a complete source page")
    page.add_argument("document", help="Full document SHA-256")
    page.add_argument("pdf_page", type=int, help="PDF page number, starting at 1")
    export = commands.add_parser("export", help="Recover the original PDF for visual review")
    export.add_argument("document", help="Full document SHA-256")
    export.add_argument("output", help="New output file; existing files are never overwritten")
    args = parser.parse_args(argv)
    try:
        if args.command == "import":
            result = import_pdf(args.pdf, args.db)
        elif args.command == "search":
            result = {
                "query": args.query,
                "matches": search_notes(
                    args.db,
                    args.query,
                    document=args.document,
                    limit=args.limit,
                ),
            }
        elif args.command == "page":
            result = get_page(args.db, args.document, args.pdf_page)
        else:
            result = export_pdf(args.db, args.document, args.output)
    except (ValueError, OSError, sqlite3.Error, PyPdfError) as error:
        print(json.dumps({"error": str(error)}), file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
