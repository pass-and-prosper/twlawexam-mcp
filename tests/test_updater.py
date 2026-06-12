# tests/test_updater.py
from twexam_mcp import updater


def test_latest_ingested_year(tmp_path):
    from twexam_mcp.cache import db
    from twexam_mcp.models.question import Question
    conn = db.connect(tmp_path / "q.db")
    db.init_schema(conn)
    db.upsert_question(conn, Question(112, "sl1", "刑法", 1, "mcq", "x", options=["a"], answer="A"))
    db.upsert_question(conn, Question(113, "sl1", "刑法", 1, "mcq", "y", options=["a"], answer="A"))
    assert updater.latest_ingested_year(conn) == 113
    conn.close()


def test_latest_ingested_year_empty_db(tmp_path):
    from twexam_mcp.cache import db
    conn = db.connect(tmp_path / "q.db")
    db.init_schema(conn)
    assert updater.latest_ingested_year(conn) is None
    conn.close()


def test_candidate_new_years(tmp_path):
    from twexam_mcp.cache import db
    from twexam_mcp.models.question import Question
    conn = db.connect(tmp_path / "q.db")
    db.init_schema(conn)
    db.upsert_question(conn, Question(112, "sl1", "刑法", 1, "mcq", "x", options=["a"], answer="A"))
    # latest = 112 → candidates are 113, 114 if current is 114
    candidates = updater.candidate_new_years(conn, current_roc_year=114)
    assert candidates == [113, 114]
    conn.close()


def test_candidate_new_years_empty_db(tmp_path):
    from twexam_mcp.cache import db
    conn = db.connect(tmp_path / "q.db")
    db.init_schema(conn)
    # Empty DB: defaults to current-1 as latest → only current year returned
    candidates = updater.candidate_new_years(conn, current_roc_year=113)
    assert candidates == [113]
    conn.close()
