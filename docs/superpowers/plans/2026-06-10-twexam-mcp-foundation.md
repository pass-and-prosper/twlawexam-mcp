# twexam-mcp Foundation + Query Surface Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a working, installable MCP server that can query a structured Taiwan legal-exam question bank (10 tools), tested against a hand-seeded fixture — locking the SQLite/FTS5 schema contract that the later ingestion pipeline (Plan 2) must fill.

**Architecture:** A FastMCP server (`server.py`) wires 10 `@mcp.tool()` functions to a thin query layer (`cache/db.py`) over an offline SQLite database with FTS5 full-text search. Dataclass models (`models/`) define the `Question` shape. The ingestion ETL (`ingest/`) is out of scope for this plan — here we seed the DB by hand to prove the query surface end-to-end.

**Tech Stack:** Python 3.11+, FastMCP SDK (`mcp`), sqlite3 (stdlib, FTS5), pytest. Mirrors the structure of `mcp-taiwan-legal-db`.

---

## Scope Note

This is **Plan 1 of 2**. Plan 2 (ingestion ETL — downloader, PDF parser, answer matcher, statute tagger, model-answer generation) is written separately, after a Phase 0 spike that downloads and inspects a real 考選部 PDF. This plan produces working, testable software on its own: a queryable MCP with seeded data.

## File Structure

```
twexam_mcp/
├── __init__.py
├── server.py            # FastMCP entry, 10 @mcp.tool() wrappers
├── config.py            # exam codes, subjects, domains, TTL
├── cache/
│   ├── __init__.py
│   └── db.py            # SQLite + FTS5: schema init, upsert, queries
├── models/
│   ├── __init__.py
│   └── question.py      # Question dataclass + (de)serialization
├── tools/
│   ├── __init__.py
│   ├── question_search.py   # search_questions, get_question
│   ├── exam_catalog.py      # list_exams, list_subjects, get_exam_paper
│   ├── answers.py           # get_answer_key, get_model_answer
│   ├── statute_xref.py      # search_by_statute, get_statute_frequency
│   └── practice.py          # random_practice
├── data/
│   └── seed.json        # hand-authored sample questions (test + demo)
└── .mcp.json
tests/
├── conftest.py
├── test_db.py
├── test_tools_search.py
├── test_tools_catalog.py
├── test_tools_answers.py
├── test_tools_statute.py
├── test_tools_practice.py
└── test_server_wiring.py
pyproject.toml
LICENSE
README.md
```

---

## Task 1: Project scaffold

**Files:**
- Create: `pyproject.toml`
- Create: `twexam_mcp/__init__.py`
- Create: `twexam_mcp/cache/__init__.py`, `twexam_mcp/models/__init__.py`, `twexam_mcp/tools/__init__.py`
- Create: `tests/__init__.py`
- Create: `.gitignore`

- [ ] **Step 1: Write `pyproject.toml`**

```toml
[project]
name = "twexam-mcp"
version = "0.1.0"
description = "Taiwan legal-exam question bank MCP server"
requires-python = ">=3.11"
dependencies = ["mcp>=1.2.0"]
license = {text = "MIT"}

[project.optional-dependencies]
dev = ["pytest>=8.0"]

[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
include = ["twexam_mcp*"]

[tool.pytest.ini_options]
testpaths = ["tests"]
```

- [ ] **Step 2: Create empty package markers**

Create these as empty files: `twexam_mcp/__init__.py`, `twexam_mcp/cache/__init__.py`, `twexam_mcp/models/__init__.py`, `twexam_mcp/tools/__init__.py`, `tests/__init__.py`.

- [ ] **Step 3: Write `.gitignore`**

```gitignore
.venv/
__pycache__/
*.pyc
twexam_mcp/data/questions.db
.pytest_cache/
*.egg-info/
```

- [ ] **Step 4: Create venv and install**

Run (Windows PowerShell):
```
py -m venv .venv
.venv\Scripts\python -m pip install -e ".[dev]"
```
Expected: installs `mcp` and `pytest` without error.

- [ ] **Step 5: Verify pytest runs (no tests yet)**

Run: `.venv\Scripts\python -m pytest -q`
Expected: `no tests ran` (exit code 5) — confirms pytest is wired.

- [ ] **Step 6: Commit**

```
git add pyproject.toml twexam_mcp tests .gitignore
git commit -m "chore: scaffold twexam-mcp package"
```

---

## Task 2: config.py — exam codes & subjects

**Files:**
- Create: `twexam_mcp/config.py`
- Test: `tests/test_config.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_config.py
from twexam_mcp import config

def test_exam_codes_cover_first_slice():
    assert config.EXAMS["sl1"] == "專門職業及技術人員高等考試律師、司法官考試第一試"
    assert config.EXAMS["sl2"] == "專門職業及技術人員高等考試律師、司法官考試第二試"

def test_subjects_nonempty():
    assert "憲法與行政法" in config.SUBJECTS["sl1"]
    assert isinstance(config.SUBJECTS["sl2"], list)

def test_moex_domain_whitelisted():
    assert "wwwq.moex.gov.tw" in config.ALLOWED_DOMAINS
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python -m pytest tests/test_config.py -v`
Expected: FAIL — `ModuleNotFoundError` / `AttributeError`.

- [ ] **Step 3: Write `config.py`**

```python
# twexam_mcp/config.py
"""Static configuration: exam codes, subjects, source domains, cache TTLs."""

# First vertical slice: 司律一試 + 二試
EXAMS = {
    "sl1": "專門職業及技術人員高等考試律師、司法官考試第一試",
    "sl2": "專門職業及技術人員高等考試律師、司法官考試第二試",
}

# Representative subjects per exam (extended during ingestion).
SUBJECTS = {
    "sl1": ["憲法與行政法", "民法與民事訴訟法", "刑法與刑事訴訟法", "商事法", "公司法、保險法"],
    "sl2": ["憲法與行政法", "國文", "民法", "民事訴訟法", "刑法", "刑事訴訟法", "公司法、保險法、證券交易法"],
}

# Live-source whitelist (used by Plan 2 ingestion; declared here for parity with legal-db).
ALLOWED_DOMAINS = {"wwwq.moex.gov.tw", "wwwc.moex.gov.tw"}

# Cache TTLs in seconds (live fetches only; the question bank itself is offline & permanent).
TTL_NEW_EXAM_CHECK = 7 * 24 * 3600
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python -m pytest tests/test_config.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```
git add twexam_mcp/config.py tests/test_config.py
git commit -m "feat: config with sl1/sl2 exam codes and subjects"
```

---

## Task 3: models/question.py — Question dataclass

**Files:**
- Create: `twexam_mcp/models/question.py`
- Test: `tests/test_models.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_models.py
from twexam_mcp.models.question import Question

def test_qid_is_composite_key():
    q = Question(year=113, exam_code="sl1", subject="憲法與行政法", q_no=5,
                 q_type="mcq", stem="下列何者...", options=["A甲", "B乙", "C丙", "D丁"],
                 answer="B")
    assert q.qid == "113-sl1-憲法與行政法-5"

def test_essay_defaults():
    q = Question(year=113, exam_code="sl2", subject="刑法", q_no=1,
                 q_type="essay", stem="試論...")
    assert q.options == []
    assert q.answer is None
    assert q.statutes == []
    assert q.model_answer is None

def test_roundtrip_dict():
    q = Question(year=113, exam_code="sl1", subject="商事法", q_no=2, q_type="mcq",
                 stem="s", options=["A", "B"], answer="A", statutes=["公司法§1"])
    assert Question.from_dict(q.to_dict()) == q
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python -m pytest tests/test_models.py -v`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Write `models/question.py`**

```python
# twexam_mcp/models/question.py
from __future__ import annotations
from dataclasses import dataclass, field, asdict


@dataclass
class Question:
    year: int                 # 民國年
    exam_code: str            # "sl1" | "sl2" (see config.EXAMS)
    subject: str              # 科目名稱
    q_no: int                 # 題號
    q_type: str               # "essay" | "mcq"
    stem: str                 # 題幹
    options: list[str] = field(default_factory=list)   # mcq 選項；essay 為空
    answer: str | None = None                          # mcq 標準答案 (e.g. "B")；essay 為 None
    statutes: list[str] = field(default_factory=list)  # 引用法條
    model_answer: str | None = None                    # essay AI 擬答；mcq 為 None

    @property
    def qid(self) -> str:
        return f"{self.year}-{self.exam_code}-{self.subject}-{self.q_no}"

    def to_dict(self) -> dict:
        d = asdict(self)
        d["qid"] = self.qid
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Question":
        return cls(
            year=d["year"], exam_code=d["exam_code"], subject=d["subject"],
            q_no=d["q_no"], q_type=d["q_type"], stem=d["stem"],
            options=list(d.get("options") or []),
            answer=d.get("answer"),
            statutes=list(d.get("statutes") or []),
            model_answer=d.get("model_answer"),
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python -m pytest tests/test_models.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```
git add twexam_mcp/models/question.py tests/test_models.py
git commit -m "feat: Question dataclass with composite qid and dict roundtrip"
```

---

## Task 4: cache/db.py — schema init + upsert + FTS sync

**Files:**
- Create: `twexam_mcp/cache/db.py`
- Test: `tests/test_db.py`
- Create: `tests/conftest.py`

- [ ] **Step 1: Write the shared fixture**

```python
# tests/conftest.py
import pytest
from twexam_mcp.cache import db
from twexam_mcp.models.question import Question

SAMPLE = [
    Question(113, "sl1", "憲法與行政法", 1, "mcq",
             "關於法律保留原則，下列敘述何者正確？",
             ["A 僅適用刑罰", "B 涉及人民權利義務應有法律依據", "C 不拘束行政", "D 僅學說"],
             answer="B", statutes=["中央法規標準法§5"]),
    Question(113, "sl1", "憲法與行政法", 2, "mcq",
             "行政處分之構成要件效力，下列何者正確？",
             ["A 無拘束力", "B 他機關應尊重", "C 得任意推翻", "D 僅及於相對人"],
             answer="B", statutes=["行政程序法§92"]),
    Question(113, "sl2", "刑法", 1, "essay",
             "甲基於殺人故意對乙開槍，試論甲之罪責。",
             statutes=["刑法§271"],
             model_answer="一、甲成立刑法第271條第1項殺人既遂罪。(AI 擬答示意)"),
    Question(112, "sl1", "民法與民事訴訟法", 3, "mcq",
             "關於消滅時效，下列何者正確？",
             ["A 期間不得約定", "B 完成後債權消滅", "C 完成後債務人得拒絕給付", "D 法院應依職權"],
             answer="C", statutes=["民法§144"]),
]

@pytest.fixture
def conn(tmp_path):
    c = db.connect(tmp_path / "t.db")
    db.init_schema(c)
    for q in SAMPLE:
        db.upsert_question(c, q)
    yield c
    c.close()
```

- [ ] **Step 2: Write the failing test**

```python
# tests/test_db.py
from twexam_mcp.cache import db

def test_get_by_qid(conn):
    q = db.get_question(conn, "113-sl1-憲法與行政法-1")
    assert q is not None and q.answer == "B"

def test_fts_search_matches_stem(conn):
    hits = db.search_questions(conn, "法律保留")
    assert any(h.qid == "113-sl1-憲法與行政法-1" for h in hits)

def test_upsert_is_idempotent(conn):
    before = len(db.search_questions(conn, "行政處分"))
    db.upsert_question(conn, db.get_question(conn, "113-sl1-憲法與行政法-2"))
    after = len(db.search_questions(conn, "行政處分"))
    assert before == after == 1
```

- [ ] **Step 3: Run test to verify it fails**

Run: `.venv\Scripts\python -m pytest tests/test_db.py -v`
Expected: FAIL — `AttributeError: module ... has no attribute 'connect'`.

- [ ] **Step 4: Write `cache/db.py` (connect, schema, upsert, get, search)**

```python
# twexam_mcp/cache/db.py
"""SQLite + FTS5 layer. The ONLY module that touches the database."""
from __future__ import annotations
import json
import sqlite3
from pathlib import Path

from twexam_mcp.models.question import Question


def connect(path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS questions (
            qid          TEXT PRIMARY KEY,
            year         INTEGER NOT NULL,
            exam_code    TEXT NOT NULL,
            subject      TEXT NOT NULL,
            q_no         INTEGER NOT NULL,
            q_type       TEXT NOT NULL,
            stem         TEXT NOT NULL,
            options      TEXT NOT NULL DEFAULT '[]',
            answer       TEXT,
            statutes     TEXT NOT NULL DEFAULT '[]',
            model_answer TEXT
        );
        CREATE VIRTUAL TABLE IF NOT EXISTS questions_fts USING fts5(
            qid UNINDEXED, stem, options, model_answer
        );
        CREATE TABLE IF NOT EXISTS statute_xref (
            statute TEXT NOT NULL,
            qid     TEXT NOT NULL,
            PRIMARY KEY (statute, qid)
        );
        CREATE INDEX IF NOT EXISTS idx_q_exam_year ON questions(exam_code, year);
        CREATE INDEX IF NOT EXISTS idx_q_subject ON questions(subject);
        """
    )
    conn.commit()


def _row_to_question(r: sqlite3.Row) -> Question:
    return Question(
        year=r["year"], exam_code=r["exam_code"], subject=r["subject"],
        q_no=r["q_no"], q_type=r["q_type"], stem=r["stem"],
        options=json.loads(r["options"]), answer=r["answer"],
        statutes=json.loads(r["statutes"]), model_answer=r["model_answer"],
    )


def upsert_question(conn: sqlite3.Connection, q: Question) -> None:
    conn.execute(
        """INSERT INTO questions
           (qid, year, exam_code, subject, q_no, q_type, stem, options, answer, statutes, model_answer)
           VALUES (?,?,?,?,?,?,?,?,?,?,?)
           ON CONFLICT(qid) DO UPDATE SET
             year=excluded.year, exam_code=excluded.exam_code, subject=excluded.subject,
             q_no=excluded.q_no, q_type=excluded.q_type, stem=excluded.stem,
             options=excluded.options, answer=excluded.answer,
             statutes=excluded.statutes, model_answer=excluded.model_answer""",
        (q.qid, q.year, q.exam_code, q.subject, q.q_no, q.q_type, q.stem,
         json.dumps(q.options, ensure_ascii=False), q.answer,
         json.dumps(q.statutes, ensure_ascii=False), q.model_answer),
    )
    conn.execute("DELETE FROM questions_fts WHERE qid=?", (q.qid,))
    conn.execute(
        "INSERT INTO questions_fts (qid, stem, options, model_answer) VALUES (?,?,?,?)",
        (q.qid, q.stem, " ".join(q.options), q.model_answer or ""),
    )
    conn.execute("DELETE FROM statute_xref WHERE qid=?", (q.qid,))
    for s in q.statutes:
        conn.execute("INSERT OR IGNORE INTO statute_xref (statute, qid) VALUES (?,?)", (s, q.qid))
    conn.commit()


def get_question(conn: sqlite3.Connection, qid: str) -> Question | None:
    r = conn.execute("SELECT * FROM questions WHERE qid=?", (qid,)).fetchone()
    return _row_to_question(r) if r else None


def search_questions(conn: sqlite3.Connection, query: str, limit: int = 20) -> list[Question]:
    rows = conn.execute(
        """SELECT q.* FROM questions_fts f JOIN questions q ON q.qid=f.qid
           WHERE questions_fts MATCH ? ORDER BY rank LIMIT ?""",
        (query, limit),
    ).fetchall()
    return [_row_to_question(r) for r in rows]
```

- [ ] **Step 5: Run test to verify it passes**

Run: `.venv\Scripts\python -m pytest tests/test_db.py -v`
Expected: PASS (3 passed).

- [ ] **Step 6: Commit**

```
git add twexam_mcp/cache/db.py tests/test_db.py tests/conftest.py
git commit -m "feat: SQLite+FTS5 layer with schema, upsert, get, search"
```

---

## Task 5: cache/db.py — catalog, statute, paper, random queries

**Files:**
- Modify: `twexam_mcp/cache/db.py` (append functions)
- Test: `tests/test_db_queries.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_db_queries.py
from twexam_mcp.cache import db

def test_list_exams(conn):
    rows = db.list_exams(conn)
    assert {"sl1", "sl2"} <= {r["exam_code"] for r in rows}
    sl1 = next(r for r in rows if r["exam_code"] == "sl1")
    assert sl1["min_year"] == 112 and sl1["max_year"] == 113

def test_list_subjects(conn):
    subs = db.list_subjects(conn, exam_code="sl1")
    assert "憲法與行政法" in subs

def test_get_exam_paper(conn):
    paper = db.get_exam_paper(conn, year=113, exam_code="sl1", subject="憲法與行政法")
    assert [q.q_no for q in paper] == [1, 2]

def test_questions_by_statute(conn):
    hits = db.questions_by_statute(conn, "行政程序法§92")
    assert [q.qid for q in hits] == ["113-sl1-憲法與行政法-2"]

def test_statute_frequency(conn):
    freq = db.statute_frequency(conn)
    assert freq["中央法規標準法§5"] == 1
    assert sum(freq.values()) == 4

def test_random_practice_deterministic_with_seed(conn):
    qs = db.random_practice(conn, exam_code="sl1", q_type="mcq", n=2, seed=42)
    assert len(qs) == 2 and all(q.q_type == "mcq" for q in qs)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python -m pytest tests/test_db_queries.py -v`
Expected: FAIL — missing attributes.

- [ ] **Step 3: Append query functions to `cache/db.py`**

```python
# --- append to twexam_mcp/cache/db.py ---
import random as _random


def list_exams(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        """SELECT exam_code, MIN(year) AS min_year, MAX(year) AS max_year, COUNT(*) AS n
           FROM questions GROUP BY exam_code ORDER BY exam_code"""
    ).fetchall()
    return [dict(r) for r in rows]


def list_subjects(conn: sqlite3.Connection, exam_code: str | None = None) -> list[str]:
    if exam_code:
        rows = conn.execute(
            "SELECT DISTINCT subject FROM questions WHERE exam_code=? ORDER BY subject",
            (exam_code,),
        ).fetchall()
    else:
        rows = conn.execute("SELECT DISTINCT subject FROM questions ORDER BY subject").fetchall()
    return [r["subject"] for r in rows]


def get_exam_paper(conn: sqlite3.Connection, year: int, exam_code: str, subject: str) -> list[Question]:
    rows = conn.execute(
        "SELECT * FROM questions WHERE year=? AND exam_code=? AND subject=? ORDER BY q_no",
        (year, exam_code, subject),
    ).fetchall()
    return [_row_to_question(r) for r in rows]


def questions_by_statute(conn: sqlite3.Connection, statute: str) -> list[Question]:
    rows = conn.execute(
        """SELECT q.* FROM statute_xref x JOIN questions q ON q.qid=x.qid
           WHERE x.statute=? ORDER BY q.year DESC, q.exam_code, q.q_no""",
        (statute,),
    ).fetchall()
    return [_row_to_question(r) for r in rows]


def statute_frequency(conn: sqlite3.Connection, exam_code: str | None = None) -> dict[str, int]:
    if exam_code:
        rows = conn.execute(
            """SELECT x.statute AS s, COUNT(*) AS n FROM statute_xref x
               JOIN questions q ON q.qid=x.qid WHERE q.exam_code=?
               GROUP BY x.statute ORDER BY n DESC""",
            (exam_code,),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT statute AS s, COUNT(*) AS n FROM statute_xref GROUP BY statute ORDER BY n DESC"
        ).fetchall()
    return {r["s"]: r["n"] for r in rows}


def random_practice(conn, exam_code=None, subject=None, q_type=None, n=5, seed=None) -> list[Question]:
    clauses, params = [], []
    if exam_code:
        clauses.append("exam_code=?"); params.append(exam_code)
    if subject:
        clauses.append("subject=?"); params.append(subject)
    if q_type:
        clauses.append("q_type=?"); params.append(q_type)
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    rows = conn.execute(f"SELECT * FROM questions {where} ORDER BY qid", params).fetchall()
    pool = [_row_to_question(r) for r in rows]
    rng = _random.Random(seed)
    rng.shuffle(pool)
    return pool[:n]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python -m pytest tests/test_db_queries.py -v`
Expected: PASS (6 passed).

- [ ] **Step 5: Commit**

```
git add twexam_mcp/cache/db.py tests/test_db_queries.py
git commit -m "feat: catalog/statute/paper/random query functions"
```

---

## Task 6: data/seed.json + loader

**Files:**
- Create: `twexam_mcp/data/seed.json`
- Modify: `twexam_mcp/cache/db.py` (add `load_seed`, `default_db_path`)
- Test: `tests/test_seed.py`

- [ ] **Step 1: Write `data/seed.json`** (same 4 questions as the test fixture, as JSON)

```json
[
  {"year":113,"exam_code":"sl1","subject":"憲法與行政法","q_no":1,"q_type":"mcq",
   "stem":"關於法律保留原則，下列敘述何者正確？",
   "options":["A 僅適用刑罰","B 涉及人民權利義務應有法律依據","C 不拘束行政","D 僅學說"],
   "answer":"B","statutes":["中央法規標準法§5"],"model_answer":null},
  {"year":113,"exam_code":"sl1","subject":"憲法與行政法","q_no":2,"q_type":"mcq",
   "stem":"行政處分之構成要件效力，下列何者正確？",
   "options":["A 無拘束力","B 他機關應尊重","C 得任意推翻","D 僅及於相對人"],
   "answer":"B","statutes":["行政程序法§92"],"model_answer":null},
  {"year":113,"exam_code":"sl2","subject":"刑法","q_no":1,"q_type":"essay",
   "stem":"甲基於殺人故意對乙開槍，試論甲之罪責。",
   "options":[],"answer":null,"statutes":["刑法§271"],
   "model_answer":"一、甲成立刑法第271條第1項殺人既遂罪。(AI 擬答示意)"},
  {"year":112,"exam_code":"sl1","subject":"民法與民事訴訟法","q_no":3,"q_type":"mcq",
   "stem":"關於消滅時效，下列何者正確？",
   "options":["A 期間不得約定","B 完成後債權消滅","C 完成後債務人得拒絕給付","D 法院應依職權"],
   "answer":"C","statutes":["民法§144"],"model_answer":null}
]
```

- [ ] **Step 2: Write the failing test**

```python
# tests/test_seed.py
from twexam_mcp.cache import db

def test_load_seed_populates(tmp_path):
    c = db.connect(tmp_path / "s.db")
    db.init_schema(c)
    n = db.load_seed(c)
    assert n == 4
    assert db.get_question(c, "113-sl2-刑法-1").q_type == "essay"
    c.close()
```

- [ ] **Step 3: Run test to verify it fails**

Run: `.venv\Scripts\python -m pytest tests/test_seed.py -v`
Expected: FAIL — no `load_seed`.

- [ ] **Step 4: Append loader to `cache/db.py`**

```python
# --- append to twexam_mcp/cache/db.py ---
from importlib import resources


def default_db_path() -> Path:
    return Path(__file__).resolve().parent.parent / "data" / "questions.db"


def load_seed(conn: sqlite3.Connection) -> int:
    raw = (resources.files("twexam_mcp.data") / "seed.json").read_text(encoding="utf-8")
    items = json.loads(raw)
    for d in items:
        upsert_question(conn, Question.from_dict(d))
    return len(items)
```

Also create `twexam_mcp/data/__init__.py` (empty) so `twexam_mcp.data` is a package for `resources.files`.

- [ ] **Step 5: Run test to verify it passes**

Run: `.venv\Scripts\python -m pytest tests/test_seed.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```
git add twexam_mcp/data/seed.json twexam_mcp/data/__init__.py twexam_mcp/cache/db.py tests/test_seed.py
git commit -m "feat: seed.json + load_seed/default_db_path"
```

---

## Task 7: tools/question_search.py — search_questions, get_question

**Files:**
- Create: `twexam_mcp/tools/question_search.py`
- Test: `tests/test_tools_search.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_tools_search.py
from twexam_mcp.tools import question_search as t

def test_search_returns_dicts(conn):
    res = t.search_questions(conn, "法律保留")
    assert res[0]["qid"] == "113-sl1-憲法與行政法-1"
    assert res[0]["answer"] == "B"

def test_get_question_found(conn):
    res = t.get_question(conn, "113-sl2-刑法-1")
    assert res["q_type"] == "essay" and res["model_answer"]

def test_get_question_missing_returns_error(conn):
    res = t.get_question(conn, "999-sl1-x-1")
    assert res == {"error": "not_found", "qid": "999-sl1-x-1"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python -m pytest tests/test_tools_search.py -v`
Expected: FAIL — module missing.

- [ ] **Step 3: Write `tools/question_search.py`**

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python -m pytest tests/test_tools_search.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```
git add twexam_mcp/tools/question_search.py tests/test_tools_search.py
git commit -m "feat: search_questions + get_question tool logic"
```

---

## Task 8: tools/exam_catalog.py — list_exams, list_subjects, get_exam_paper

**Files:**
- Create: `twexam_mcp/tools/exam_catalog.py`
- Test: `tests/test_tools_catalog.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_tools_catalog.py
from twexam_mcp.tools import exam_catalog as t

def test_list_exams_includes_label(conn):
    res = t.list_exams(conn)
    sl1 = next(r for r in res if r["exam_code"] == "sl1")
    assert sl1["label"].startswith("專門職業") and sl1["max_year"] == 113

def test_list_subjects(conn):
    assert "刑法" in t.list_subjects(conn, "sl2")

def test_get_exam_paper(conn):
    res = t.get_exam_paper(conn, 113, "sl1", "憲法與行政法")
    assert [q["q_no"] for q in res] == [1, 2]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python -m pytest tests/test_tools_catalog.py -v`
Expected: FAIL.

- [ ] **Step 3: Write `tools/exam_catalog.py`**

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python -m pytest tests/test_tools_catalog.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```
git add twexam_mcp/tools/exam_catalog.py tests/test_tools_catalog.py
git commit -m "feat: list_exams/list_subjects/get_exam_paper tool logic"
```

---

## Task 9: tools/answers.py — get_answer_key, get_model_answer

**Files:**
- Create: `twexam_mcp/tools/answers.py`
- Test: `tests/test_tools_answers.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_tools_answers.py
from twexam_mcp.tools import answers as t

def test_answer_key_for_paper(conn):
    res = t.get_answer_key(conn, 113, "sl1", "憲法與行政法")
    assert res == {"1": "B", "2": "B"}

def test_model_answer_for_essay(conn):
    res = t.get_model_answer(conn, "113-sl2-刑法-1")
    assert res["model_answer"].startswith("一、")
    assert res["disclaimer"]

def test_model_answer_for_mcq_is_error(conn):
    res = t.get_model_answer(conn, "113-sl1-憲法與行政法-1")
    assert res["error"] == "not_an_essay"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python -m pytest tests/test_tools_answers.py -v`
Expected: FAIL.

- [ ] **Step 3: Write `tools/answers.py`**

```python
# twexam_mcp/tools/answers.py
from twexam_mcp.cache import db

DISCLAIMER = "AI 擬答為機器生成，非官方解答，不得作為應試或法律意見依據，請向權威來源驗證。"


def get_answer_key(conn, year: int, exam_code: str, subject: str) -> dict:
    paper = db.get_exam_paper(conn, year, exam_code, subject)
    return {str(q.q_no): q.answer for q in paper if q.q_type == "mcq" and q.answer}


def get_model_answer(conn, qid: str) -> dict:
    q = db.get_question(conn, qid)
    if q is None:
        return {"error": "not_found", "qid": qid}
    if q.q_type != "essay":
        return {"error": "not_an_essay", "qid": qid}
    return {"qid": qid, "model_answer": q.model_answer, "disclaimer": DISCLAIMER}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python -m pytest tests/test_tools_answers.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```
git add twexam_mcp/tools/answers.py tests/test_tools_answers.py
git commit -m "feat: get_answer_key + get_model_answer tool logic"
```

---

## Task 10: tools/statute_xref.py — search_by_statute, get_statute_frequency

**Files:**
- Create: `twexam_mcp/tools/statute_xref.py`
- Test: `tests/test_tools_statute.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_tools_statute.py
from twexam_mcp.tools import statute_xref as t

def test_search_by_statute(conn):
    res = t.search_by_statute(conn, "行政程序法§92")
    assert [q["qid"] for q in res] == ["113-sl1-憲法與行政法-2"]

def test_statute_frequency_sorted(conn):
    res = t.get_statute_frequency(conn)
    assert res["items"][0]["count"] >= res["items"][-1]["count"]
    assert res["total"] == 4
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python -m pytest tests/test_tools_statute.py -v`
Expected: FAIL.

- [ ] **Step 3: Write `tools/statute_xref.py`**

```python
# twexam_mcp/tools/statute_xref.py
from twexam_mcp.cache import db


def search_by_statute(conn, statute: str) -> list[dict]:
    return [q.to_dict() for q in db.questions_by_statute(conn, statute)]


def get_statute_frequency(conn, exam_code: str | None = None) -> dict:
    freq = db.statute_frequency(conn, exam_code)
    items = [{"statute": s, "count": n} for s, n in freq.items()]
    return {"items": items, "total": sum(freq.values())}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python -m pytest tests/test_tools_statute.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```
git add twexam_mcp/tools/statute_xref.py tests/test_tools_statute.py
git commit -m "feat: search_by_statute + get_statute_frequency tool logic"
```

---

## Task 11: tools/practice.py — random_practice

**Files:**
- Create: `twexam_mcp/tools/practice.py`
- Test: `tests/test_tools_practice.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_tools_practice.py
from twexam_mcp.tools import practice as t

def test_random_practice_count_and_filter(conn):
    res = t.random_practice(conn, exam_code="sl1", q_type="mcq", n=2, seed=1)
    assert len(res) == 2 and all(q["q_type"] == "mcq" for q in res)

def test_random_practice_hides_answer_when_requested(conn):
    res = t.random_practice(conn, exam_code="sl1", q_type="mcq", n=1, seed=1, hide_answer=True)
    assert "answer" not in res[0] and "model_answer" not in res[0]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python -m pytest tests/test_tools_practice.py -v`
Expected: FAIL.

- [ ] **Step 3: Write `tools/practice.py`**

```python
# twexam_mcp/tools/practice.py
from twexam_mcp.cache import db


def random_practice(conn, exam_code=None, subject=None, q_type=None,
                    n=5, seed=None, hide_answer=False) -> list[dict]:
    qs = db.random_practice(conn, exam_code, subject, q_type, n, seed)
    out = []
    for q in qs:
        d = q.to_dict()
        if hide_answer:
            d.pop("answer", None)
            d.pop("model_answer", None)
        out.append(d)
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python -m pytest tests/test_tools_practice.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```
git add twexam_mcp/tools/practice.py tests/test_tools_practice.py
git commit -m "feat: random_practice tool logic"
```

---

## Task 12: server.py — FastMCP wiring of all 10 tools

**Files:**
- Create: `twexam_mcp/server.py`
- Test: `tests/test_server_wiring.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_server_wiring.py
import twexam_mcp.server as srv

EXPECTED = {
    "search_questions", "get_question", "list_exams", "list_subjects",
    "get_exam_paper", "get_answer_key", "get_model_answer",
    "search_by_statute", "get_statute_frequency", "random_practice",
}

def test_all_ten_tools_registered():
    names = set(srv.mcp._tool_manager._tools.keys())
    assert EXPECTED <= names, EXPECTED - names

def test_get_conn_uses_seed_when_db_absent(tmp_path, monkeypatch):
    target = tmp_path / "questions.db"
    monkeypatch.setattr(srv.db, "default_db_path", lambda: target)
    srv._CONN = None
    conn = srv.get_conn()
    assert conn.execute("SELECT COUNT(*) FROM questions").fetchone()[0] == 4
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python -m pytest tests/test_server_wiring.py -v`
Expected: FAIL — module missing.

- [ ] **Step 3: Write `server.py`**

```python
# twexam_mcp/server.py
"""FastMCP entry point. Only wiring — no SQL, no LLM calls here."""
from mcp.server.fastmcp import FastMCP

from twexam_mcp.cache import db
from twexam_mcp.tools import (
    question_search, exam_catalog, answers, statute_xref, practice,
)

mcp = FastMCP("twexam")
_CONN = None


def get_conn():
    """Lazily open the question DB; fall back to in-memory seed if no DB file exists yet."""
    global _CONN
    if _CONN is not None:
        return _CONN
    path = db.default_db_path()
    if path.exists():
        _CONN = db.connect(path)
    else:
        _CONN = db.connect(":memory:")
        db.init_schema(_CONN)
        db.load_seed(_CONN)
    return _CONN


@mcp.tool()
def search_questions(query: str, limit: int = 20) -> list[dict]:
    """全文搜尋歷屆考題（匹配題幹/選項/擬答）。"""
    return question_search.search_questions(get_conn(), query, limit)


@mcp.tool()
def get_question(qid: str) -> dict:
    """以 qid（年-考試-科目-題號）取得單題結構化內容。"""
    return question_search.get_question(get_conn(), qid)


@mcp.tool()
def list_exams() -> list[dict]:
    """列出可查的考試別與年度範圍。"""
    return exam_catalog.list_exams(get_conn())


@mcp.tool()
def list_subjects(exam_code: str | None = None) -> list[str]:
    """列出科目（可選 exam_code 篩選）。"""
    return exam_catalog.list_subjects(get_conn(), exam_code)


@mcp.tool()
def get_exam_paper(year: int, exam_code: str, subject: str) -> list[dict]:
    """取整份試卷（某年·某考試·某科目全部題目）。"""
    return exam_catalog.get_exam_paper(get_conn(), year, exam_code, subject)


@mcp.tool()
def get_answer_key(year: int, exam_code: str, subject: str) -> dict:
    """取某份試卷的測驗題標準答案（題號→答案）。"""
    return answers.get_answer_key(get_conn(), year, exam_code, subject)


@mcp.tool()
def get_model_answer(qid: str) -> dict:
    """取申論題 AI 擬答（含免責聲明）。"""
    return answers.get_model_answer(get_conn(), qid)


@mcp.tool()
def search_by_statute(statute: str) -> list[dict]:
    """按法條反查考過哪些題。"""
    return statute_xref.search_by_statute(get_conn(), statute)


@mcp.tool()
def get_statute_frequency(exam_code: str | None = None) -> dict:
    """法條考頻統計（可選 exam_code）。"""
    return statute_xref.get_statute_frequency(get_conn(), exam_code)


@mcp.tool()
def random_practice(exam_code: str | None = None, subject: str | None = None,
                    q_type: str | None = None, n: int = 5,
                    seed: int | None = None, hide_answer: bool = False) -> list[dict]:
    """依條件抽題練習（hide_answer 可隱藏答案/擬答）。"""
    return practice.random_practice(get_conn(), exam_code, subject, q_type, n, seed, hide_answer)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python -m pytest tests/test_server_wiring.py -v`
Expected: PASS (2 passed).

Note: if `srv.mcp._tool_manager._tools` raises due to an SDK version change, fall back to `await srv.mcp.list_tools()` inside an `asyncio.run(...)` and assert on `{t.name for t in ...}`. Verify the actual attribute with `.venv\Scripts\python -c "from twexam_mcp.server import mcp; print(dir(mcp))"` first.

- [ ] **Step 5: Commit**

```
git add twexam_mcp/server.py tests/test_server_wiring.py
git commit -m "feat: FastMCP server wiring all 10 tools + seed fallback"
```

---

## Task 13: Full suite + live MCP smoke test

**Files:**
- Test: full suite

- [ ] **Step 1: Run the entire test suite**

Run: `.venv\Scripts\python -m pytest -q`
Expected: all tests PASS (no failures, no errors).

- [ ] **Step 2: Smoke-test the server starts and lists tools**

Run:
```
.venv\Scripts\python -c "from twexam_mcp.server import mcp, get_conn; get_conn(); import asyncio; print(sorted(t.name for t in asyncio.run(mcp.list_tools())))"
```
Expected: prints the 10 tool names.

- [ ] **Step 3: Smoke-test one tool end-to-end against seed**

Run:
```
.venv\Scripts\python -c "from twexam_mcp.server import get_conn; from twexam_mcp.tools import question_search as t; print(t.search_questions(get_conn(), '法律保留')[0]['qid'])"
```
Expected: `113-sl1-憲法與行政法-1`

- [ ] **Step 4: Commit (if any fixes were needed)**

```
git add -A
git commit -m "test: full suite green + MCP smoke test"
```

---

## Task 14: Packaging — .mcp.json, LICENSE, README

**Files:**
- Create: `.mcp.json`
- Create: `LICENSE`
- Create: `README.md`

- [ ] **Step 1: Write `.mcp.json`** (Windows venv path; document the POSIX variant in README)

```json
{
  "mcpServers": {
    "twexam": {
      "command": ".venv\\Scripts\\python.exe",
      "args": ["-m", "twexam_mcp.server"]
    }
  }
}
```

- [ ] **Step 2: Write `LICENSE`** — standard MIT License text, copyright holder "twexam-mcp contributors", year 2026.

- [ ] **Step 3: Write `README.md`**

Include: one-line description; install (`py -m venv .venv` + `pip install -e .`); Claude Code registration (built-in `.mcp.json`); Claude Desktop registration snippet (with POSIX `.venv/bin/python` note); the 10 tools as a table; data-source note (考選部 政府公開資料); **disclaimer** (AI 擬答 non-official, not legal/exam advice); pointer that the question bank is populated by Plan 2's ingestion pipeline and ships with a small seed for demo.

- [ ] **Step 4: Verify registration loads (manual)**

Run: `.venv\Scripts\python -m twexam_mcp.server` then Ctrl-C.
Expected: process starts (waits on stdio) without import errors.

- [ ] **Step 5: Commit**

```
git add .mcp.json LICENSE README.md
git commit -m "docs: packaging — .mcp.json, MIT LICENSE, README with disclaimer"
```

---

## Self-Review (completed during planning)

**Spec coverage:**
- 10 MCP tools → Tasks 7–12 ✅ (search_questions, get_question, list_exams, list_subjects, get_exam_paper, get_answer_key, get_model_answer, search_by_statute, get_statute_frequency, random_practice)
- SQLite + FTS5 offline store → Tasks 4–5 ✅
- 法條↔題目反查 + 考頻統計 (exceeds legal-db citation graph) → Tasks 5, 10 ✅
- Composite primary key `(year, exam_code, subject, q_no)` → Task 3 `qid` ✅
- Packaging parity (.mcp.json, pipx-able, MIT, disclaimer) → Tasks 1, 14 ✅
- Cost-discipline / PDF parsing / OCR / model-answer generation → **deferred to Plan 2** (ingestion); seed data stands in here ✅
- Auto-update (updater.py) → **deferred to Plan 2** (depends on live download) ✅

**Placeholder scan:** No TBD/TODO in code steps; every step has runnable code or an exact command. README prose content (Task 14 Step 3) is enumerated, not "write a README". ✅

**Type consistency:** `Question` fields and `qid` format identical across Tasks 3–12. `db.*` signatures match their tool callers. Tool functions all take `conn` first and return `dict`/`list[dict]`. `get_conn()`/`_CONN`/`default_db_path()`/`load_seed()` names consistent between Task 6 and Task 12. ✅

---

## Out of scope (Plan 2 — Ingestion ETL)

Phase 0 spike (download + parse one real 考選部 PDF), `ingest/downloader.py`, `ingest/pdf_parser.py` (+ Gemini OCR fallback), `ingest/answer_matcher.py`, `ingest/statute_tagger.py` (Gemini Flash, labor tier), `ingest/model_answer_gen.py` (Batch API, generate-once), `updater.py` (new-exam-season detection), and the three-layer ingestion audit (L1 static / L2 coverage / L3 runtime). These fill the real `questions.db` that this plan's schema defines.
