# tests/test_model_answer_gen.py
from twexam_mcp.cache import db
from twexam_mcp.ingest import model_answer_gen as mag
from twexam_mcp.models.question import Question


def test_generates_only_for_essays_without_answer(tmp_path, monkeypatch):
    conn = db.connect(tmp_path / "q.db")
    db.init_schema(conn)
    db.upsert_question(conn, Question(113, "sl2", "刑法", 1, "essay", "試論甲罪責"))
    db.upsert_question(conn, Question(113, "sl2", "刑法", 2, "essay", "試論乙罪責",
                                      model_answer="既有擬答"))   # already has one
    db.upsert_question(conn, Question(113, "sl1", "刑法", 1, "mcq", "x", options=["a", "b"], answer="A"))

    monkeypatch.setattr(mag, "_batch_generate", lambda prompts: ["擬答:" + p[:4] for p in prompts])
    monkeypatch.setattr(mag, "_count_only", False, raising=False)

    n = mag.generate(conn, dry_run=False)
    assert n == 1                                   # only the essay without an answer
    assert db.get_question(conn, "113-sl2-刑法-1").model_answer.startswith("擬答:")
    assert db.get_question(conn, "113-sl2-刑法-2").model_answer == "既有擬答"  # untouched
    conn.close()


def test_dry_run_counts_without_calling(tmp_path, monkeypatch):
    conn = db.connect(tmp_path / "q.db")
    db.init_schema(conn)
    db.upsert_question(conn, Question(113, "sl2", "刑法", 1, "essay", "試論甲罪責"))

    called = []
    monkeypatch.setattr(mag, "_batch_generate", lambda prompts: called.append(1) or [])

    n = mag.generate(conn, dry_run=True)
    assert n == 1 and called == []                  # dry-run never calls the API
    conn.close()
