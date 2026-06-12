# twexam_mcp/ingest/pipeline.py
from __future__ import annotations
from pathlib import Path

from twexam_mcp.ingest import downloader, pdf_parser, answer_key, statute_tagger
from twexam_mcp.cache import db
from twexam_mcp.models.question import Question


def ingest_exam(conn, year_roc: int, exam: str, pdf_root) -> int:
    """Ingest one (year, exam) into the open db connection. Returns #questions upserted."""
    code, subjects = downloader.discover(year_roc, exam)
    if code is None:
        raise ValueError(f"no 司律 {exam} exam found for ROC year {year_roc}")
    answers_by_daihao: dict[str, list[str]] = {}
    booklet = downloader.download_answer_booklet(pdf_root, code)
    if booklet is not None:
        answers_by_daihao = answer_key.parse_answer_booklet(booklet)

    count = 0
    for sref in subjects:
        qpath = downloader.download(pdf_root, sref, "Q")
        if exam == "sl1":
            paper = pdf_parser.parse_mcq_paper(qpath)
            ans = answers_by_daihao.get(paper.daihao, [])
            for q in paper.questions:
                q.year = year_roc
                q.answer = ans[q.q_no - 1] if q.q_no - 1 < len(ans) else None
                q.statutes = statute_tagger.extract_statutes(q.stem)
                db.upsert_question(conn, q)
                count += 1
        else:
            paper = pdf_parser.parse_essay_paper(qpath)
            for q in paper.questions:
                q.year = year_roc
                q.statutes = statute_tagger.extract_statutes(q.stem)
                db.upsert_question(conn, q)
                count += 1
    return count
