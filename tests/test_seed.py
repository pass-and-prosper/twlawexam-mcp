# tests/test_seed.py
from twexam_mcp.cache import db

def test_load_seed_populates(tmp_path):
    c = db.connect(tmp_path / "s.db")
    db.init_schema(c)
    n = db.load_seed(c)
    assert n == 4
    assert db.get_question(c, "113-sl2-刑法-1").q_type == "essay"
    c.close()
