# twexam_mcp/tools/practice.py
from twexam_mcp.cache import db
from twexam_mcp.tools.answers import DISCLAIMER


def random_practice(conn, exam_code=None, subject=None, q_type=None,
                    n=5, seed=None, hide_answer=False) -> list[dict]:
    qs = db.random_practice(conn, exam_code, subject, q_type, n, seed)
    return _serialize(qs, hide_answer)


def essay_exam_by_topic(conn, topic_point=None, topic_subject=None, show_answer=True) -> dict:
    """考點申論題卷：把某考點（或整個子科目）的所有申論題一次考出來。

    回傳一份「考卷」物件：題目照原文完整列出，預設直接附 AI 擬答（show_answer=True，
    對應使用者「要可以直接看答案」）；show_answer=False 則隱藏擬答供先行作答。
    擬答存在時一律附上免責聲明。
    """
    qs = db.essay_exam_by_topic(conn, topic_point, topic_subject)
    questions = []
    for q in qs:
        d = q.to_dict()
        if not show_answer:
            d.pop("model_answer", None)
        questions.append(d)
    result = {
        "topic_point": topic_point,
        "topic_subject": topic_subject,
        "count": len(questions),
        "questions": questions,
    }
    if show_answer:
        result["disclaimer"] = DISCLAIMER
    return result


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
