# twexam_mcp/updater.py
"""Detect newly-published exam seasons that have not yet been ingested."""
from __future__ import annotations


def latest_ingested_year(conn) -> int | None:
    """Return the maximum ROC year present in questions, or None if DB is empty."""
    r = conn.execute("SELECT MAX(year) AS y FROM questions").fetchone()
    return r["y"] if r and r["y"] is not None else None


def candidate_new_years(conn, current_roc_year: int) -> list[int]:
    """Years between (latest-ingested + 1) and current_roc_year that may have new exams.

    If the DB is empty, assumes the previous year is the latest and returns
    [current_roc_year] so the caller fetches at minimum the current year.
    """
    latest = latest_ingested_year(conn) or (current_roc_year - 1)
    return list(range(latest + 1, current_roc_year + 1))
