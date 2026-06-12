# tests/test_server_wiring.py
import asyncio
import twexam_mcp.server as srv

EXPECTED = {
    "search_questions", "get_question", "list_exams", "list_subjects",
    "get_exam_paper", "get_answer_key", "get_model_answer",
    "search_by_statute", "get_statute_frequency", "random_practice",
}


def test_all_ten_tools_registered():
    """Assert all 10 expected tools are registered, using the public list_tools() API."""
    names = {t.name for t in asyncio.run(srv.mcp.list_tools())}
    assert EXPECTED <= names, f"Missing tools: {EXPECTED - names}"


def test_get_conn_uses_seed_when_db_absent(tmp_path, monkeypatch):
    """When the DB file doesn't exist, get_conn() should fall back to an in-memory
    DB seeded with the 4 bundled seed questions."""
    target = tmp_path / "questions.db"
    monkeypatch.setattr(srv.db, "default_db_path", lambda: target)
    srv._CONN = None
    conn = srv.get_conn()
    count = conn.execute("SELECT COUNT(*) FROM questions").fetchone()[0]
    assert count == 4
    # Reset global state so other tests are not affected
    srv._CONN = None
