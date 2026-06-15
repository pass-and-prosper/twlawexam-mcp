# tests/test_essay_exam.py
"""考點申論題卷（模擬考）：把某考點/子科目的所有申論題一次考出來，附擬答。"""
import pytest
from twexam_mcp.cache import db
from twexam_mcp.models.question import Question
from twexam_mcp.tools import practice as t
from twexam_mcp.tools.answers import DISCLAIMER

# 3 classified essays on 董事責任 + 1 on another 考點, across two years.
_ESSAYS = [
    Question(113, "sl2", "公司法、保險法、證券交易法", 1, "essay",
             "甲公司董事乙未盡善良管理人注意義務致公司受損，試論其責任。",
             statutes=["公司法§23"], model_answer="一、乙違反忠實義務…(擬答)",
             topic_subject="公司法、保險法與證券交易法", topic_point="董事責任"),
    Question(112, "sl2", "公司法、保險法、證券交易法", 2, "essay",
             "董事與公司交易之利益衝突如何規範？",
             statutes=["公司法§206"], model_answer="一、利益迴避…(擬答)",
             topic_subject="公司法、保險法與證券交易法", topic_point="董事責任"),
    Question(114, "sl2", "公司法、保險法、證券交易法", 1, "essay",
             "董事對第三人之損害賠償責任要件為何？",
             statutes=["公司法§23"], model_answer="一、對第三人責任…(擬答)",
             topic_subject="公司法、保險法與證券交易法", topic_point="董事責任"),
    Question(113, "sl2", "公司法、保險法、證券交易法", 3, "essay",
             "試論保險代位之要件與範圍。",
             statutes=["保險法§53"], model_answer="一、保險代位…(擬答)",
             topic_subject="公司法、保險法與證券交易法", topic_point="保險代位"),
]


@pytest.fixture
def econn(conn):
    for q in _ESSAYS:
        db.upsert_question(conn, q)
    return conn


def test_pulls_all_essays_for_a_topic_point(econn):
    res = t.essay_exam_by_topic(econn, topic_point="董事責任")
    # all 3 董事責任 essays, none from 保險代位; no random cap
    assert res["count"] == 3
    assert {q["topic_point"] for q in res["questions"]} == {"董事責任"}
    assert all(q["q_type"] == "essay" for q in res["questions"])


def test_answers_shown_by_default_with_disclaimer(econn):
    res = t.essay_exam_by_topic(econn, topic_point="董事責任")
    assert all(q["model_answer"] for q in res["questions"])
    assert res["disclaimer"] == DISCLAIMER


def test_show_answer_false_hides_model_answer(econn):
    res = t.essay_exam_by_topic(econn, topic_point="董事責任", show_answer=False)
    assert all("model_answer" not in q for q in res["questions"])
    assert "disclaimer" not in res  # nothing to disclaim when answers hidden


def test_stable_order_newest_year_first(econn):
    res = t.essay_exam_by_topic(econn, topic_point="董事責任")
    years = [q["year"] for q in res["questions"]]
    assert years == sorted(years, reverse=True)


def test_subject_level_pulls_whole_subject(econn):
    res = t.essay_exam_by_topic(econn, topic_subject="公司法、保險法與證券交易法")
    # 3 董事責任 + 1 保險代位 = 4
    assert res["count"] == 4


def test_requires_at_least_one_filter(econn):
    with pytest.raises(ValueError):
        t.essay_exam_by_topic(econn)
