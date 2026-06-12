# twexam_mcp/tools/review.py
"""Weak-point engine: record attempts, surface weak 考點, drive targeted practice."""
from twexam_mcp.cache import db


def record_answer(conn, qid, answer=None, self_correct=None) -> dict:
    """Grade + log one attempt and update its spaced-repetition schedule."""
    return db.record_answer(conn, qid, answer, self_correct)


def get_weak_topics(conn, q_type="mcq", min_attempts=1, limit=20) -> list[dict]:
    rows = db.get_weak_topics(conn, q_type, min_attempts, limit)
    return [
        {"topic_subject": r[0], "topic_point": r[1],
         "attempted": r[2], "correct": r[3], "accuracy": r[4]}
        for r in rows
    ]


def get_progress(conn, q_type="mcq") -> dict:
    return db.get_progress(conn, q_type)


def practice_weak(conn, n=5, subject=None, q_type="mcq", hide_answer=True) -> list[dict]:
    qs = db.practice_weak(conn, n, subject, q_type)
    out = []
    for q in qs:
        d = q.to_dict()
        if hide_answer:
            d.pop("answer", None)
            d.pop("model_answer", None)
        out.append(d)
    return out


def reset_progress(conn) -> dict:
    db.reset_progress(conn)
    return {"status": "reset", "message": "所有作答記錄與複習排程已清空"}


def get_readiness(conn, target=0.60, q_type="mcq", daily=25) -> dict:
    return db.get_readiness(conn, target=target, q_type=q_type, daily=daily)


def get_topic_primer(conn, topic_point) -> dict:
    """考點重點提示：做題前先讀的核心法條/判決/釋字/學說/陷阱。"""
    return db.get_topic_primer(conn, topic_point)
