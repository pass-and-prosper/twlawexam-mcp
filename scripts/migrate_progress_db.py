#!/usr/bin/env python
"""One-time / idempotent migration: split personal practice history out of the
single-file ``questions.db`` into a separate, git-ignored ``progress.db``.

Older layouts kept ``attempts`` + ``review_state`` inside the bank, which risks
committing/publishing practice history. The new layout attaches a sibling
``progress.db`` as ``prog`` and stores those two tables there only. This script
moves any legacy rows over and removes the tables from the bank.

Safe to re-run: if the bank no longer has the legacy tables, it just ensures the
progress schema exists and reports 0 moved. A pre-migration backup of the bank is
written next to it (``*.premigrate.bak``, git-ignored).
"""
from __future__ import annotations
import shutil
import sys
from pathlib import Path

from twexam_mcp.cache import db


def _has_main_table(conn, name: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM main.sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone() is not None


def main() -> int:
    bank = db.default_db_path()
    prog = db.default_progress_path()
    if not bank.exists():
        print(f"ERROR: bank not found: {bank}", file=sys.stderr)
        return 1

    # safety backup of the bank (sidecar WAL data is read live via the connection)
    bak = bank.with_name("questions.db.premigrate.bak")
    shutil.copy2(bank, bak)
    print(f"[migrate] backed up bank -> {bak.name}")

    conn = db.connect(bank)        # attaches prog (creates progress.db lazily)
    db.init_schema(conn)           # ensures prog.attempts / prog.review_state exist

    moved_a = moved_r = 0
    with conn:                     # writes only to prog -> single-DB, atomic
        if _has_main_table(conn, "attempts"):
            rows = conn.execute(
                "SELECT qid, user_answer, is_correct, answered_at FROM main.attempts"
            ).fetchall()
            for r in rows:
                conn.execute(
                    "INSERT INTO prog.attempts (qid, user_answer, is_correct, answered_at) "
                    "VALUES (?,?,?,?)",
                    (r["qid"], r["user_answer"], r["is_correct"], r["answered_at"]),
                )
            moved_a = len(rows)
        if _has_main_table(conn, "review_state"):
            rows = conn.execute(
                "SELECT qid, last_answer, last_correct, n_attempts, n_correct, streak, "
                "interval_days, due_date, updated_at FROM main.review_state"
            ).fetchall()
            for r in rows:
                conn.execute(
                    "INSERT OR REPLACE INTO prog.review_state "
                    "(qid, last_answer, last_correct, n_attempts, n_correct, streak, "
                    "interval_days, due_date, updated_at) VALUES (?,?,?,?,?,?,?,?,?)",
                    (r["qid"], r["last_answer"], r["last_correct"], r["n_attempts"],
                     r["n_correct"], r["streak"], r["interval_days"], r["due_date"],
                     r["updated_at"]),
                )
            moved_r = len(rows)

    # drop legacy tables from the bank, then compact it
    with conn:
        conn.execute("DROP TABLE IF EXISTS main.attempts")
        conn.execute("DROP TABLE IF EXISTS main.review_state")
    conn.isolation_level = None        # VACUUM must run outside a transaction
    conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    conn.execute("VACUUM")
    conn.isolation_level = ""

    # verify
    pa = conn.execute("SELECT COUNT(*) FROM prog.attempts").fetchone()[0]
    pr = conn.execute("SELECT COUNT(*) FROM prog.review_state").fetchone()[0]
    nq = conn.execute("SELECT COUNT(*) FROM main.questions").fetchone()[0]
    bank_dirty = _has_main_table(conn, "attempts") or _has_main_table(conn, "review_state")
    conn.close()

    print(f"[migrate] moved {moved_a} attempts, {moved_r} review_state -> {prog.name}")
    print(f"[migrate] progress.db now: attempts={pa} review_state={pr}")
    print(f"[migrate] bank questions={nq}; bank still has progress tables? {bank_dirty}")
    if bank_dirty:
        print("ERROR: bank still carries progress tables after migration", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
