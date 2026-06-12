# twexam_mcp/tools/statute_xref.py
from twexam_mcp.cache import db


def search_by_statute(conn, statute: str) -> list[dict]:
    return [q.to_dict() for q in db.questions_by_statute(conn, statute)]


def get_statute_frequency(conn, exam_code: str | None = None) -> dict:
    freq = db.statute_frequency(conn, exam_code)
    items = [{"statute": s, "count": n} for s, n in freq.items()]
    return {"items": items, "total": sum(freq.values())}
