# tests/test_audit.py
from twexam_mcp.cache import db
from twexam_mcp.ingest import audit


def test_audit_flags_missing_answers(conn):   # conn fixture from Plan 1 has seed data
    report = audit.audit(conn)
    assert "total_questions" in report
    assert "mcq_missing_answer" in report
    assert "subjects_zero_statutes" in report
    assert isinstance(report["per_exam"], dict)
