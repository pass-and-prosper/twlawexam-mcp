# twexam_mcp/ingest/audit.py
from __future__ import annotations


def audit(conn) -> dict:
    """L1/L2 audit over questions.db. Flags silent gaps (spike + CLAUDE.md L4/L6)."""
    cur = conn.cursor()
    total = cur.execute("SELECT COUNT(*) FROM questions").fetchone()[0]
    mcq_missing = cur.execute(
        "SELECT COUNT(*) FROM questions WHERE q_type='mcq' AND (answer IS NULL OR answer='')"
    ).fetchone()[0]
    per_exam = {}
    for r in cur.execute(
        "SELECT exam_code, COUNT(*) n, SUM(q_type='mcq') mcq, SUM(q_type='essay') essay "
        "FROM questions GROUP BY exam_code"
    ).fetchall():
        per_exam[r["exam_code"]] = {"total": r["n"], "mcq": r["mcq"], "essay": r["essay"]}
    zero_statute = [
        r["subject"] for r in cur.execute(
            "SELECT q.subject, COUNT(x.qid) c FROM questions q "
            "LEFT JOIN statute_xref x ON x.qid=q.qid GROUP BY q.subject HAVING c=0"
        ).fetchall()
    ]
    return {
        "total_questions": total,
        "mcq_missing_answer": mcq_missing,
        "subjects_zero_statutes": zero_statute,
        "per_exam": per_exam,
    }
