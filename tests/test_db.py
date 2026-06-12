# tests/test_db.py
from twexam_mcp.cache import db

def test_get_by_qid(conn):
    q = db.get_question(conn, "113-sl1-憲法與行政法-1")
    assert q is not None and q.answer == "B"

def test_fts_search_matches_stem(conn):
    hits = db.search_questions(conn, "法律保留")
    assert any(h.qid == "113-sl1-憲法與行政法-1" for h in hits)

def test_upsert_is_idempotent(conn):
    before = len(db.search_questions(conn, "行政處分"))
    db.upsert_question(conn, db.get_question(conn, "113-sl1-憲法與行政法-2"))
    after = len(db.search_questions(conn, "行政處分"))
    assert before == after == 1


def test_search_query_shorter_than_3_returns_empty(conn):
    # SQLite's trigram tokenizer cannot match queries < 3 chars; the guard
    # must return [] immediately rather than letting SQLite silently return
    # nothing (which would hide a potential future tokenizer change).
    assert db.search_questions(conn, "法") == []
    assert db.search_questions(conn, "ab") == []
    assert db.search_questions(conn, "  ") == []
    assert db.search_questions(conn, "") == []
