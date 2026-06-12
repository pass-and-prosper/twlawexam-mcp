# tests/test_tools_answers.py
from twexam_mcp.tools import answers as t

def test_answer_key_for_paper(conn):
    res = t.get_answer_key(conn, 113, "sl1", "憲法與行政法")
    assert res == {"1": "B", "2": "B"}

def test_model_answer_for_essay(conn):
    res = t.get_model_answer(conn, "113-sl2-刑法-1")
    assert res["model_answer"].startswith("一、")
    assert res["disclaimer"]

def test_model_answer_for_mcq_is_error(conn):
    res = t.get_model_answer(conn, "113-sl1-憲法與行政法-1")
    assert res["error"] == "not_an_essay"
