#!/usr/bin/env python
"""Build a distributable wheel that ships a CLEAN question bank (no personal data).

Personal practice history (attempts / review_state) now lives in a SEPARATE,
git-ignored ``progress.db`` (attached as ``prog`` at runtime) — never in the
shippable bank ``questions.db``. So the bank is clean *by construction* and the
wheel cannot leak practice history:

  * ``questions.db`` (package-data) holds only the question bank.
  * ``progress.db`` is not declared as package-data, so ``pip wheel`` excludes it.

This script therefore just builds the wheel, after a defensive check that the
bank really carries no personal-progress rows (guards against a contaminated DB
copied in from an older single-file layout).
"""
from __future__ import annotations
import sqlite3
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "twexam_mcp" / "data" / "questions.db"
DIST = ROOT / "dist"


def _personal_rows(db: Path) -> int:
    """Rows of practice history sitting in the bank. Should always be 0 now."""
    # Fixed, literal COUNT statements (no f-string / interpolation) per the
    # zero-injection rule; table names cannot be bound with `?`.
    _COUNTS = {
        "attempts": "SELECT COUNT(*) FROM attempts",
        "review_state": "SELECT COUNT(*) FROM review_state",
    }
    conn = sqlite3.connect(db)
    try:
        n = 0
        for t, count_sql in _COUNTS.items():
            exists = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (t,)
            ).fetchone()
            if exists:
                n += conn.execute(count_sql).fetchone()[0]
        return n
    finally:
        conn.close()


def main() -> int:
    if not DB.exists():
        print(f"ERROR: {DB} not found", file=sys.stderr)
        return 1

    leaked = _personal_rows(DB)
    if leaked:
        print(
            f"ERROR: {DB} contains {leaked} personal-progress row(s) — refusing to "
            "ship. Practice history must live only in the separate progress.db. "
            "Run scripts/migrate_progress_db.py (it moves the rows out and VACUUMs) "
            "before building. Do NOT just DROP the tables: with secure_delete off, "
            "dropped rows linger in free pages and would still ship.",
            file=sys.stderr,
        )
        return 2

    # Rewrite the bank file so free pages (anything ever deleted) do not ship.
    conn = sqlite3.connect(DB)
    try:
        conn.execute("VACUUM")
    finally:
        conn.close()

    # `uv build` produces both sdist and wheel (what PyPI wants). Without uv,
    # use the `build` frontend; refuse to silently produce only a wheel.
    import shutil
    if shutil.which("uv"):
        subprocess.run(["uv", "build", "--out-dir", str(DIST)], cwd=ROOT, check=True)
    else:
        try:
            import build  # noqa: F401
        except ImportError:
            print("ERROR: need `uv` or `pip install build` to produce sdist+wheel",
                  file=sys.stderr)
            return 3
        subprocess.run([sys.executable, "-m", "build", "--outdir", str(DIST)],
                       cwd=ROOT, check=True)
    made = sorted(p.name for p in DIST.iterdir() if p.suffix in (".whl", ".gz"))
    print(f"[build] {made} written to dist/ — bank VACUUMed, no practice history bundled")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
