"""Where does personal progress (attempts / review_state) live?

For a `uvx` / `pip install` user the package directory is replaced on every
upgrade, so progress.db must NOT sit next to questions.db there. These tests
pin the resolution order: env override -> legacy sibling (if it exists) ->
per-user data dir. Remove any branch in default_progress_path() and one of
these goes red.
"""
from pathlib import Path

from twexam_mcp.cache import db


def _fake_bank(tmp_path, monkeypatch):
    bank = tmp_path / "pkg" / "data" / "questions.db"
    bank.parent.mkdir(parents=True)
    bank.write_bytes(b"")
    monkeypatch.setattr(db, "default_db_path", lambda: bank.resolve())
    return bank


def test_env_override_wins(tmp_path, monkeypatch):
    _fake_bank(tmp_path, monkeypatch)
    target = tmp_path / "elsewhere" / "p.db"
    monkeypatch.setenv("TWEXAM_PROGRESS_DB", str(target))
    assert db.default_progress_path() == target


def test_legacy_sibling_kept_when_present(tmp_path, monkeypatch):
    bank = _fake_bank(tmp_path, monkeypatch)
    monkeypatch.delenv("TWEXAM_PROGRESS_DB", raising=False)
    sibling = bank.with_name("progress.db")
    sibling.write_bytes(b"")
    assert db.default_progress_path() == sibling


def test_fresh_install_uses_user_data_dir_not_package_dir(tmp_path, monkeypatch):
    bank = _fake_bank(tmp_path, monkeypatch)
    monkeypatch.delenv("TWEXAM_PROGRESS_DB", raising=False)
    home = tmp_path / "home"
    monkeypatch.setenv("LOCALAPPDATA", str(home / "AppData" / "Local"))   # Windows
    monkeypatch.setenv("XDG_DATA_HOME", str(home / ".local" / "share"))   # Linux
    monkeypatch.setattr(Path, "home", staticmethod(lambda: home))          # macOS
    p = db.default_progress_path()
    assert p.name == "progress.db"
    assert p.parent.name == "twlawexam-mcp"
    assert bank.parent not in p.parents, "progress must not live inside the package dir"
    assert p.parent.is_dir(), "data dir is created so sqlite can ATTACH there"


def test_connect_on_default_bank_attaches_resolved_progress(tmp_path, monkeypatch):
    """connect(default_db_path()) with no progress_path must use the resolved
    location, not blindly the sibling."""
    bank = _fake_bank(tmp_path, monkeypatch)
    bank.unlink()  # let sqlite create a real (empty) bank file
    target = tmp_path / "prog" / "p.db"
    target.parent.mkdir()
    monkeypatch.setenv("TWEXAM_PROGRESS_DB", str(target))
    conn = db.connect(bank)
    try:
        rows = {r[1]: r[2] for r in conn.execute("PRAGMA database_list")}
    finally:
        conn.close()
    assert Path(rows["prog"]).resolve() == target.resolve()


def test_connect_on_other_bank_keeps_sibling(tmp_path, monkeypatch):
    """Test fixtures and ad-hoc banks (not the bundled one) keep the old
    sibling behaviour so temp-dir tests stay hermetic."""
    monkeypatch.setenv("TWEXAM_PROGRESS_DB", str(tmp_path / "should-not-be-used.db"))
    other = tmp_path / "q.db"
    conn = db.connect(other)
    try:
        rows = {r[1]: r[2] for r in conn.execute("PRAGMA database_list")}
    finally:
        conn.close()
    assert Path(rows["prog"]) == other.with_name("progress.db")
