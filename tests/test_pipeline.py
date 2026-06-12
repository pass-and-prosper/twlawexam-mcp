# tests/test_pipeline.py
from pathlib import Path
from twexam_mcp.ingest import pipeline, refs
from twexam_mcp.cache import db

FIXDIR = Path(__file__).parent / "fixtures" / "pdf"


def test_ingest_one_mcq_subject(tmp_path, monkeypatch):
    # stub discovery -> one subject; stub download -> fixture files
    sref = refs.SubjectRef("113110", "301", "0101", "1")
    monkeypatch.setattr(pipeline.downloader, "discover", lambda y, e: ("113110", [sref]))
    monkeypatch.setattr(pipeline.downloader, "download",
                        lambda root, ref, t: FIXDIR / "sl1_113110_c301_s0101.pdf")
    monkeypatch.setattr(pipeline.downloader, "download_answer_booklet",
                        lambda root, code: FIXDIR / "sl1_113110_answerkey.pdf")
    conn = db.connect(tmp_path / "q.db")
    db.init_schema(conn)
    n = pipeline.ingest_exam(conn, year_roc=113, exam="sl1", pdf_root=tmp_path)
    assert n == 75
    # Look up Q1 by position (q_no=1) since the PDF subject may contain a private-use
    # glyph (U+E129) that makes the exact string differ from a hardcoded literal.
    row = conn.execute(
        "SELECT * FROM questions WHERE year=113 AND exam_code='sl1' AND q_no=1"
    ).fetchone()
    assert row is not None
    assert row["answer"] == "D"   # matched from answer booklet (代號 2301)
    assert "貨物應許自由流通" in row["stem"]
    # Q1 stem is "關於貨物應許自由流通之憲法規定，下列敘述何者錯誤？"
    # extract_statutes finds no article citation in this stem → statutes == []
    import json
    assert json.loads(row["statutes"]) == []
    conn.close()


def test_ingest_one_essay_subject(tmp_path, monkeypatch):
    sref = refs.SubjectRef("113111", "301", "0102", "1")
    monkeypatch.setattr(pipeline.downloader, "discover", lambda y, e: ("113111", [sref]))
    monkeypatch.setattr(pipeline.downloader, "download",
                        lambda root, ref, t: FIXDIR / "sl2_113111_c301_s0102.pdf")
    monkeypatch.setattr(pipeline.downloader, "download_answer_booklet",
                        lambda root, code: None)
    conn = db.connect(tmp_path / "q.db")
    db.init_schema(conn)
    n = pipeline.ingest_exam(conn, year_roc=113, exam="sl2", pdf_root=tmp_path)
    assert n >= 1
    q1 = db.get_question(conn, "113-sl2-憲法與行政法-1")
    assert q1.q_type == "essay" and q1.answer is None and q1.model_answer is None
    conn.close()
