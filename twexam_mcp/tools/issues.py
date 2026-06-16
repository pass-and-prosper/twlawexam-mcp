# twexam_mcp/tools/issues.py
"""申論爭點索引工具：以『學說/實務交鋒點』為骨架的真實考點。"""
from twexam_mcp.cache import db


def get_issue_distribution(conn, topic_subject=None) -> list[dict]:
    """爭點熱度排行：各爭點考過幾題（申論真實考點分布）。可選 topic_subject 篩選。"""
    return [{"issue": r[0], "n_questions": r[1], "topic_subject": r[2]}
            for r in db.issue_distribution(conn, topic_subject)]


def search_by_issue(conn, issue: str) -> list[dict]:
    """依爭點找題：某爭點考過哪幾題，附各題該爭點的學說/實務見解。"""
    return db.questions_by_issue(conn, issue)


def get_issues(conn, qid: str) -> list[dict]:
    """取某申論題拆出的所有爭點（爭點名＋學說＋實務）。"""
    return db.get_issues(conn, qid)


def get_issue_primer(conn, issue: str) -> dict:
    """取某申論爭點的重點包：辨識訊號＋前置觀念＋考點重點。"""
    return db.get_issue_primer(conn, issue)
