# twexam_mcp/tools/question_search.py
"""MCP tool logic for searching/fetching questions. Pure functions over a db connection."""
from twexam_mcp.cache import db


def search_questions(conn, query: str, limit: int = 20) -> list[dict]:
    return [q.to_dict() for q in db.search_questions(conn, query, limit)]


def get_question(conn, qid: str) -> dict:
    q = db.get_question(conn, qid)
    if q is None:
        return {"error": "not_found", "qid": qid}
    return q.to_dict()
