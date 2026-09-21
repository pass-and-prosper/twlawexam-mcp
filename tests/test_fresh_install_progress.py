"""A fresh install ships a prebuilt bank, so init_schema() never runs on the
normal server path. The attached progress DB starts empty; connect() must
create its tables or every progress tool crashes with
"no such table: prog.review_state" (seen live via `uvx` before this fix)."""
import shutil

from twexam_mcp.cache import db


def _prebuilt_bank(tmp_path):
    """Simulate the shipped bank: schema + seed built once, then reopened."""
    bank = tmp_path / "questions.db"
    c = db.connect(bank)
    db.init_schema(c)
    db.load_seed(c)
    c.close()
    # throw away the progress.db that the build step created next to it
    (tmp_path / "progress.db").unlink()
    return bank


def test_connect_creates_progress_tables_on_fresh_progress_db(tmp_path):
    bank = _prebuilt_bank(tmp_path)
    c = db.connect(bank)  # no init_schema, like server.get_conn on a shipped bank
    try:
        assert db.get_progress(c)["total_attempts"] == 0
        tables = {r[0] for r in c.execute(
            "SELECT name FROM prog.sqlite_master WHERE type='table'")}
    finally:
        c.close()
    assert {"attempts", "review_state"} <= tables


def test_record_answer_works_on_fresh_install(tmp_path):
    bank = _prebuilt_bank(tmp_path)
    c = db.connect(bank)
    try:
        qid = c.execute("SELECT qid FROM questions LIMIT 1").fetchone()[0]
        db.record_answer(c, qid, "A")
        assert c.execute("SELECT COUNT(*) FROM prog.attempts").fetchone()[0] == 1
    finally:
        c.close()


def test_init_schema_and_connect_share_one_progress_ddl(tmp_path):
    """Guard against the two DDL copies drifting apart: whatever init_schema
    produces in prog must equal what connect() produces from scratch."""
    a = db.connect(tmp_path / "a.db"); db.init_schema(a)
    b = db.connect(tmp_path / "b.db")
    try:
        ddl = lambda c: sorted(r[0] for r in c.execute(
            "SELECT sql FROM prog.sqlite_master WHERE sql IS NOT NULL"))
        assert ddl(a) == ddl(b)
    finally:
        a.close(); b.close()
