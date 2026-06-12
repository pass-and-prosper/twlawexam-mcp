# twexam_mcp/ingest/run.py
"""CLI entry-point: ingest one or more (year, exam) combos into questions.db.

Usage:
    python -m twexam_mcp.ingest.run --years 113 112 111
    python -m twexam_mcp.ingest.run --years 113 --exams sl1
    python -m twexam_mcp.ingest.run --years 113 --pdf-root /mnt/pdfs
"""
from __future__ import annotations
import argparse
from pathlib import Path

from twexam_mcp.cache import db
from twexam_mcp.ingest import pipeline, audit


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Ingest 司律 exams into questions.db")
    ap.add_argument("--years", type=int, nargs="+", required=True,
                    help="ROC years to ingest, e.g. 113 112 111")
    ap.add_argument("--exams", nargs="+", default=["sl1", "sl2"],
                    choices=["sl1", "sl2"],
                    help="Exam tier(s) to ingest (default: both sl1 and sl2)")
    ap.add_argument("--pdf-root", default=str(db.default_db_path().parent / "pdfs"),
                    help="Directory for cached PDF downloads")
    args = ap.parse_args(argv)

    conn = db.connect(db.default_db_path())
    db.init_schema(conn)

    total = 0
    for y in args.years:
        for ex in args.exams:
            try:
                n = pipeline.ingest_exam(conn, y, ex, args.pdf_root)
                print(f"[ingest] {y} {ex}: {n} questions")
                total += n
            except Exception as e:   # one exam failure must NOT abort the rest
                print(f"[ingest] {y} {ex}: ERROR {type(e).__name__}: {e}")

    rep = audit.audit(conn)
    print(f"[audit] {rep}")
    conn.close()
    print(f"[ingest] DONE total={total}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
