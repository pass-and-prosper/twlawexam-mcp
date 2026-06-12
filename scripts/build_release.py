#!/usr/bin/env python
"""Build a distributable wheel that ships a CLEAN question DB (no personal data).

The wheel bundles twexam_mcp/data/questions.db. That file also holds the local
user's practice history (attempts / review_state). Publishing it as-is would leak
that history, so this script:

  1. backs up the live DB,
  2. clears attempts + review_state in the build copy,
  3. builds the wheel (pip wheel),
  4. restores the live DB unconditionally (try/finally) — your progress is never
     lost even if the build fails.
"""
from __future__ import annotations
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "twexam_mcp" / "data" / "questions.db"
BAK = DB.with_name("questions.db.userbak")
DIST = ROOT / "dist"


def main() -> int:
    if not DB.exists():
        print(f"ERROR: {DB} not found", file=sys.stderr)
        return 1

    shutil.copy2(DB, BAK)  # preserve the user's full DB
    try:
        conn = sqlite3.connect(DB)
        with conn:
            conn.execute("DELETE FROM attempts")
            conn.execute("DELETE FROM review_state")
        conn.close()
        print("[build] cleared personal practice history in the build copy")

        subprocess.run(
            [sys.executable, "-m", "pip", "wheel", ".", "--no-deps", "-w", str(DIST)],
            cwd=ROOT, check=True,
        )
        print("[build] wheel written to dist/ with a clean DB")
    finally:
        shutil.move(str(BAK), str(DB))  # restore the user's full DB no matter what
        print("[build] restored your live DB — practice history intact")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
