# tests/test_issues.py
"""申論爭點索引：store/distribution/search round-trip."""
from twexam_mcp.cache import db
from twexam_mcp.models.question import Question
from twexam_mcp.tools import issues as t


def _seed(conn):
    db.upsert_question(conn, Question(
        114, "sl2", "刑法與刑事訴訟法", 1, "essay", "甲開槍...試論不能未遂。",
        topic_subject="刑法與刑事訴訟法", topic_point="未遂", model_answer="..."))
    db.upsert_question(conn, Question(
        112, "sl2", "刑法與刑事訴訟法", 2, "essay", "乙下毒...是否不能未遂？",
        topic_subject="刑法與刑事訴訟法", topic_point="未遂", model_answer="..."))


def test_replace_and_get_issues(conn):
    _seed(conn)
    n = db.replace_issues(conn, "114-sl2-刑法與刑事訴訟法-1", [
        {"issue": "不能未遂之判斷標準",
         "doctrines": ["具體危險說", "重大無知說（印象說）"],
         "practice": ["最高法院97年度台上字第XXXX號"]},
        {"issue": "中止未遂之自願性", "doctrines": ["主觀說", "客觀說"], "practice": []},
    ])
    assert n == 2
    got = t.get_issues(conn, "114-sl2-刑法與刑事訴訟法-1")
    assert got[0]["issue"] == "不能未遂之判斷標準"
    assert "具體危險說" in got[0]["doctrines"]
    # idempotent: re-store replaces, not appends
    db.replace_issues(conn, "114-sl2-刑法與刑事訴訟法-1", [{"issue": "X", "doctrines": [], "practice": []}])
    assert len(t.get_issues(conn, "114-sl2-刑法與刑事訴訟法-1")) == 1


def test_issue_distribution_counts_distinct_questions(conn):
    _seed(conn)
    db.replace_issues(conn, "114-sl2-刑法與刑事訴訟法-1",
                      [{"issue": "不能未遂之判斷標準", "doctrines": [], "practice": []}])
    db.replace_issues(conn, "112-sl2-刑法與刑事訴訟法-2",
                      [{"issue": "不能未遂之判斷標準", "doctrines": [], "practice": []}])
    dist = t.get_issue_distribution(conn)
    top = dist[0]
    assert top["issue"] == "不能未遂之判斷標準" and top["n_questions"] == 2


def test_search_by_issue_returns_each_questions_doctrines(conn):
    _seed(conn)
    db.replace_issues(conn, "114-sl2-刑法與刑事訴訟法-1",
                      [{"issue": "不能未遂之判斷標準", "doctrines": ["具體危險說"], "practice": []}])
    hits = t.search_by_issue(conn, "不能未遂之判斷標準")
    assert len(hits) == 1
    assert hits[0]["qid"] == "114-sl2-刑法與刑事訴訟法-1"
    assert "具體危險說" in hits[0]["doctrines"]
