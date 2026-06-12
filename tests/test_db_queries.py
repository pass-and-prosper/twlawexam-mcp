# tests/test_db_queries.py
from twexam_mcp.cache import db

def test_list_exams(conn):
    rows = db.list_exams(conn)
    assert {"sl1", "sl2"} <= {r["exam_code"] for r in rows}
    sl1 = next(r for r in rows if r["exam_code"] == "sl1")
    assert sl1["min_year"] == 112 and sl1["max_year"] == 113

def test_list_subjects(conn):
    subs = db.list_subjects(conn, exam_code="sl1")
    assert "憲法與行政法" in subs

def test_get_exam_paper(conn):
    paper = db.get_exam_paper(conn, year=113, exam_code="sl1", subject="憲法與行政法")
    assert [q.q_no for q in paper] == [1, 2]

def test_questions_by_statute(conn):
    hits = db.questions_by_statute(conn, "行政程序法§92")
    assert [q.qid for q in hits] == ["113-sl1-憲法與行政法-2"]

def test_statute_frequency(conn):
    freq = db.statute_frequency(conn)
    assert freq["中央法規標準法§5"] == 1
    assert sum(freq.values()) == 4

def test_random_practice_deterministic_with_seed(conn):
    qs = db.random_practice(conn, exam_code="sl1", q_type="mcq", n=2, seed=42)
    assert len(qs) == 2 and all(q.q_type == "mcq" for q in qs)
