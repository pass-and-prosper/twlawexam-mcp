# twexam_mcp/tools/practice.py
from twexam_mcp.cache import db


def random_practice(conn, exam_code=None, subject=None, q_type=None,
                    n=5, seed=None, hide_answer=False) -> list[dict]:
    qs = db.random_practice(conn, exam_code, subject, q_type, n, seed)
    return _serialize(qs, hide_answer)


def practice_by_topic(conn, topic_point, topic_subject=None, q_type=None,
                      n=5, seed=None, hide_answer=False) -> list[dict]:
    qs = db.random_practice_by_topic(conn, topic_point, topic_subject, q_type, n, seed)
    return _serialize(qs, hide_answer)


def _serialize(qs, hide_answer: bool) -> list[dict]:
    out = []
    for q in qs:
        d = q.to_dict()
        if hide_answer:
            d.pop("answer", None)
            d.pop("model_answer", None)
        out.append(d)
    return out
