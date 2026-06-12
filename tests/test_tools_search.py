# tests/test_tools_search.py
from twexam_mcp.tools import question_search as t

def test_search_returns_dicts(conn):
    res = t.search_questions(conn, "法律保留")
    assert res[0]["qid"] == "113-sl1-憲法與行政法-1"
    assert res[0]["answer"] == "B"

def test_get_question_found(conn):
    res = t.get_question(conn, "113-sl2-刑法-1")
    assert res["q_type"] == "essay" and res["model_answer"]

def test_get_question_missing_returns_error(conn):
    res = t.get_question(conn, "999-sl1-x-1")
    assert res == {"error": "not_found", "qid": "999-sl1-x-1"}
