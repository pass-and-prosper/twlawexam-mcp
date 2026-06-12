# tests/test_tools_catalog.py
from twexam_mcp.tools import exam_catalog as t

def test_list_exams_includes_label(conn):
    res = t.list_exams(conn)
    sl1 = next(r for r in res if r["exam_code"] == "sl1")
    assert sl1["label"].startswith("專門職業") and sl1["max_year"] == 113

def test_list_subjects(conn):
    assert "刑法" in t.list_subjects(conn, "sl2")

def test_get_exam_paper(conn):
    res = t.get_exam_paper(conn, 113, "sl1", "憲法與行政法")
    assert [q["q_no"] for q in res] == [1, 2]
