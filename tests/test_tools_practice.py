# tests/test_tools_practice.py
from twexam_mcp.tools import practice as t

def test_random_practice_count_and_filter(conn):
    res = t.random_practice(conn, exam_code="sl1", q_type="mcq", n=2, seed=1)
    assert len(res) == 2 and all(q["q_type"] == "mcq" for q in res)

def test_random_practice_hides_answer_when_requested(conn):
    res = t.random_practice(conn, exam_code="sl1", q_type="mcq", n=1, seed=1, hide_answer=True)
    assert "answer" not in res[0] and "model_answer" not in res[0]
