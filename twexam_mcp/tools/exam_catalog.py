# twexam_mcp/tools/exam_catalog.py
from twexam_mcp.cache import db
from twexam_mcp import config


def list_exams(conn) -> list[dict]:
    out = []
    for r in db.list_exams(conn):
        out.append({**r, "label": config.EXAMS.get(r["exam_code"], r["exam_code"])})
    return out


def list_subjects(conn, exam_code: str | None = None) -> list[str]:
    return db.list_subjects(conn, exam_code)


def get_exam_paper(conn, year: int, exam_code: str, subject: str) -> list[dict]:
    return [q.to_dict() for q in db.get_exam_paper(conn, year, exam_code, subject)]
