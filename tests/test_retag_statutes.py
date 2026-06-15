# tests/test_retag_statutes.py
"""retag_all_statutes must recover essay 條號 from the 擬答 (not just the stem)."""
from twexam_mcp.cache import db
from twexam_mcp.models.question import Question


def _essay_with_answer_in_model_only():
    # stem cites NO 條號; all citations live in the 擬答 — the exact bug case
    return Question(
        114, "sl2", "公司法、保險法、證券交易法", 1, "essay",
        "甲兼任B公司監察人是否合法？董事責任如何？",  # no 條號 here
        statutes=[],
        model_answer="依公司法第200條（§227準用）裁判解任；證交法§157短線交易；釋字第604號。",
        topic_subject="公司法、保險法與證券交易法", topic_point="董事責任",
    )


def test_retag_recovers_statutes_from_model_answer(conn):
    q = _essay_with_answer_in_model_only()
    db.upsert_question(conn, q)
    # before: stem-only tagging left it empty
    assert db.get_question(conn, q.qid).statutes == []

    result = db.retag_all_statutes(conn)
    tagged = db.get_question(conn, q.qid).statutes
    assert "公司法第200條" in tagged
    assert "證券交易法第157條" in tagged   # 證交法 → canonical
    assert "釋字第604號" in tagged
    assert result[q.qid] == tagged


def test_retag_makes_search_by_statute_work(conn):
    db.upsert_question(conn, _essay_with_answer_in_model_only())
    db.retag_all_statutes(conn)
    # statute_xref rebuilt → reverse lookup now finds the essay
    hits = db.questions_by_statute(conn, "公司法第200條")
    assert any(h.topic_point == "董事責任" for h in hits)
