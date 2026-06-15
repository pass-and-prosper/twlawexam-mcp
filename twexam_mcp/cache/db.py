# twexam_mcp/cache/db.py
"""SQLite + FTS5 layer. The ONLY module that touches the database."""
from __future__ import annotations
import json
import sqlite3
from datetime import date, timedelta
from pathlib import Path

from twexam_mcp.models.question import Question


def _progress_path_for(bank_path) -> str:
    """Sibling path of the personal-progress DB for a given bank DB path.

    Personal practice history (attempts / review_state) lives in a SEPARATE,
    git-ignored ``progress.db`` next to the shippable question bank, so it can
    never be committed/published alongside ``questions.db``. An in-memory bank
    gets an in-memory progress DB (ephemeral, e.g. the seed-fallback path and
    some tests)."""
    s = str(bank_path)
    if s == ":memory:":
        return ":memory:"
    return str(Path(s).with_name("progress.db"))


def connect(path, progress_path=None) -> sqlite3.Connection:
    # NOTE: isolation_level="" (the default) enables Python's implicit
    # transaction management, which is required for `with conn:` to issue
    # BEGIN/COMMIT/ROLLBACK correctly.  Do NOT pass isolation_level=None
    # (autocommit) — that silently breaks the atomicity of upsert_question
    # and load_seed: every execute() would auto-commit immediately, so a
    # crash mid-upsert would leave FTS / xref rows orphaned with no rollback.
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    # Attach the personal-progress DB as `prog`. attempts/review_state live ONLY
    # here (never in the bank), so practice history is physically incapable of
    # entering version control. record_answer / reset_progress write only to
    # `prog`, so each write transaction touches a single database (atomic
    # regardless of journal mode); cross-DB JOINs against main.questions are
    # read-only and fine.
    conn.execute("ATTACH DATABASE ? AS prog", (progress_path or _progress_path_for(path),))
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
            model_answer TEXT,
            topic_subject TEXT,
            topic_point   TEXT
        );
        CREATE VIRTUAL TABLE IF NOT EXISTS questions_fts USING fts5(
            qid UNINDEXED, stem, options, model_answer,
            tokenize='trigram'
        );
        CREATE TABLE IF NOT EXISTS statute_xref (
            statute TEXT NOT NULL,
            qid     TEXT NOT NULL,
            PRIMARY KEY (statute, qid)
        );
        CREATE INDEX IF NOT EXISTS idx_q_exam_year ON questions(exam_code, year);
        CREATE INDEX IF NOT EXISTS idx_q_subject ON questions(subject);
        CREATE INDEX IF NOT EXISTS idx_q_topic ON questions(topic_point);

        -- Weak-point engine: immutable attempt log + per-question SR state.
        -- Personal progress data; lives ONLY in the attached, git-ignored
        -- prog (progress.db) — never in the shippable bank (questions.db).
        -- All reads/writes of these two tables are qualified with `prog.`.
        CREATE TABLE IF NOT EXISTS prog.attempts (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            qid         TEXT NOT NULL,
            user_answer TEXT,
            is_correct  INTEGER,          -- 1/0; NULL = essay self-grade omitted
            answered_at TEXT NOT NULL      -- ISO date (YYYY-MM-DD)
        );
        CREATE INDEX IF NOT EXISTS prog.idx_attempts_qid ON attempts(qid);
        CREATE TABLE IF NOT EXISTS prog.review_state (
            qid          TEXT PRIMARY KEY,
            last_answer  TEXT,
            last_correct INTEGER,
            n_attempts   INTEGER NOT NULL DEFAULT 0,
            n_correct    INTEGER NOT NULL DEFAULT 0,
            streak       INTEGER NOT NULL DEFAULT 0,   -- consecutive correct
            interval_days INTEGER NOT NULL DEFAULT 0,
            due_date     TEXT,                          -- ISO date next due
            updated_at   TEXT
        );
        CREATE INDEX IF NOT EXISTS prog.idx_review_due ON review_state(due_date);

        -- Per-考點 study primer: must-know 法條/判決/釋字/學說/陷阱, read before drilling.
        CREATE TABLE IF NOT EXISTS topic_notes (
            topic_point TEXT PRIMARY KEY,
            primer      TEXT NOT NULL,
            updated_at  TEXT
        );
        """
    )
    conn.commit()


def _row_to_question(r: sqlite3.Row) -> Question:
    keys = r.keys()  # seed-fallback DBs may predate the topic columns
    return Question(
        year=r["year"], exam_code=r["exam_code"], subject=r["subject"],
        q_no=r["q_no"], q_type=r["q_type"], stem=r["stem"],
        options=json.loads(r["options"]), answer=r["answer"],
        statutes=json.loads(r["statutes"]), model_answer=r["model_answer"],
        topic_subject=r["topic_subject"] if "topic_subject" in keys else None,
        topic_point=r["topic_point"] if "topic_point" in keys else None,
    )


def _upsert(conn: sqlite3.Connection, q: Question) -> None:
    """Execute all DML for one question without managing the transaction.

    Callers are responsible for wrapping this in a ``with conn:`` block so
    that a failure mid-sequence rolls back every table atomically (questions,
    questions_fts, statute_xref).  Do NOT call conn.commit() here.
    """
    conn.execute(
        """INSERT INTO questions
           (qid, year, exam_code, subject, q_no, q_type, stem, options, answer, statutes, model_answer,
            topic_subject, topic_point)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
           ON CONFLICT(qid) DO UPDATE SET
             year=excluded.year, exam_code=excluded.exam_code, subject=excluded.subject,
             q_no=excluded.q_no, q_type=excluded.q_type, stem=excluded.stem,
             options=excluded.options, answer=excluded.answer,
             statutes=excluded.statutes, model_answer=excluded.model_answer,
             topic_subject=COALESCE(excluded.topic_subject, questions.topic_subject),
             topic_point=COALESCE(excluded.topic_point, questions.topic_point)""",
        (q.qid, q.year, q.exam_code, q.subject, q.q_no, q.q_type, q.stem,
         json.dumps(q.options, ensure_ascii=False), q.answer,
         json.dumps(q.statutes, ensure_ascii=False), q.model_answer,
         q.topic_subject, q.topic_point),
    )
    conn.execute("DELETE FROM questions_fts WHERE qid=?", (q.qid,))
    conn.execute(
        "INSERT INTO questions_fts (qid, stem, options, model_answer) VALUES (?,?,?,?)",
        (q.qid, q.stem, " ".join(q.options), q.model_answer or ""),
    )
    conn.execute("DELETE FROM statute_xref WHERE qid=?", (q.qid,))
    for s in q.statutes:
        conn.execute("INSERT OR IGNORE INTO statute_xref (statute, qid) VALUES (?,?)", (s, q.qid))


def upsert_question(conn: sqlite3.Connection, q: Question) -> None:
    """Atomically insert or replace one question across all three tables.

    Wraps :func:`_upsert` in a ``with conn:`` block so that any failure
    between the questions INSERT and the statute_xref inserts is rolled back
    entirely — preventing orphaned FTS / xref rows.
    """
    with conn:
        _upsert(conn, q)


def get_question(conn: sqlite3.Connection, qid: str) -> Question | None:
    r = conn.execute("SELECT * FROM questions WHERE qid=?", (qid,)).fetchone()
    return _row_to_question(r) if r else None


def search_questions(conn: sqlite3.Connection, query: str, limit: int = 20) -> list[Question]:
    """Full-text search over question stem, options, and model answer.

    Uses SQLite's trigram tokenizer, which requires at least 3 characters to
    produce any matches.  Queries shorter than 3 characters (after stripping
    whitespace) are rejected early and return an empty list rather than letting
    SQLite silently return nothing.
    """
    if len(query.strip()) < 3:
        return []
    rows = conn.execute(
        """SELECT q.* FROM questions_fts f JOIN questions q ON q.qid=f.qid
           WHERE questions_fts MATCH ? ORDER BY rank LIMIT ?""",
        (query, limit),
    ).fetchall()
    return [_row_to_question(r) for r in rows]


# --- catalog / statute / paper / random queries ---
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
    # Pre-written parameterised queries for every filter combination (no f-string / string concat).
    _SQL: dict[tuple[bool, bool, bool], str] = {
        (False, False, False): "SELECT * FROM questions ORDER BY qid",
        (True,  False, False): "SELECT * FROM questions WHERE exam_code=? ORDER BY qid",
        (False, True,  False): "SELECT * FROM questions WHERE subject=? ORDER BY qid",
        (False, False, True ): "SELECT * FROM questions WHERE q_type=? ORDER BY qid",
        (True,  True,  False): "SELECT * FROM questions WHERE exam_code=? AND subject=? ORDER BY qid",
        (True,  False, True ): "SELECT * FROM questions WHERE exam_code=? AND q_type=? ORDER BY qid",
        (False, True,  True ): "SELECT * FROM questions WHERE subject=? AND q_type=? ORDER BY qid",
        (True,  True,  True ): "SELECT * FROM questions WHERE exam_code=? AND subject=? AND q_type=? ORDER BY qid",
    }
    key = (exam_code is not None, subject is not None, q_type is not None)
    params = [v for v in (exam_code, subject, q_type) if v is not None]
    rows = conn.execute(_SQL[key], params).fetchall()
    pool = [_row_to_question(r) for r in rows]
    rng = _random.Random(seed)
    rng.shuffle(pool)
    return pool[:n]


def random_practice_by_topic(conn, topic_point, topic_subject=None, q_type=None,
                             n=5, seed=None) -> list[Question]:
    """Draw random questions filtered by classified 考點 (topic_point)."""
    _SQL: dict[tuple[bool, bool], str] = {
        (False, False): "SELECT * FROM questions WHERE topic_point=? ORDER BY qid",
        (True,  False): "SELECT * FROM questions WHERE topic_point=? AND topic_subject=? ORDER BY qid",
        (False, True ): "SELECT * FROM questions WHERE topic_point=? AND q_type=? ORDER BY qid",
        (True,  True ): "SELECT * FROM questions WHERE topic_point=? AND topic_subject=? AND q_type=? ORDER BY qid",
    }
    key = (topic_subject is not None, q_type is not None)
    params = [topic_point] + [v for v in (topic_subject, q_type) if v is not None]
    rows = conn.execute(_SQL[key], params).fetchall()
    pool = [_row_to_question(r) for r in rows]
    rng = _random.Random(seed)
    rng.shuffle(pool)
    return pool[:n]


def essay_exam_by_topic(conn, topic_point=None, topic_subject=None) -> list[Question]:
    """Return ALL essay (申論) questions for a 考點 or 子科目, in stable exam order.

    Unlike random_practice_by_topic, this draws the COMPLETE set — no random
    sampling, no n cap — so the user can sit a whole topic's essays in one go
    ("一次考出來"). At least one of topic_point / topic_subject must be given.
    Ordered newest year first for a consistent paper layout.
    """
    if not topic_point and not topic_subject:
        raise ValueError("essay_exam_by_topic requires topic_point or topic_subject")
    _SQL: dict[tuple[bool, bool], str] = {
        (True,  False): ("SELECT * FROM questions WHERE q_type='essay' AND topic_point=? "
                         "ORDER BY year DESC, subject, q_no"),
        (True,  True ): ("SELECT * FROM questions WHERE q_type='essay' AND topic_point=? AND topic_subject=? "
                         "ORDER BY year DESC, subject, q_no"),
        (False, True ): ("SELECT * FROM questions WHERE q_type='essay' AND topic_subject=? "
                         "ORDER BY year DESC, subject, q_no"),
    }
    key = (topic_point is not None, topic_subject is not None)
    params = [v for v in (topic_point, topic_subject) if v is not None]
    rows = conn.execute(_SQL[key], params).fetchall()
    return [_row_to_question(r) for r in rows]


def topic_distribution(conn, q_type=None, exam_code=None) -> list[tuple]:
    """Return (topic_subject, topic_point, count) rows, most-frequent first."""
    _SQL: dict[tuple[bool, bool], str] = {
        (False, False): ("SELECT topic_subject, topic_point, COUNT(*) FROM questions "
                         "WHERE topic_subject IS NOT NULL GROUP BY topic_subject, topic_point ORDER BY 3 DESC"),
        (True,  False): ("SELECT topic_subject, topic_point, COUNT(*) FROM questions "
                         "WHERE topic_subject IS NOT NULL AND q_type=? GROUP BY topic_subject, topic_point ORDER BY 3 DESC"),
        (False, True ): ("SELECT topic_subject, topic_point, COUNT(*) FROM questions "
                         "WHERE topic_subject IS NOT NULL AND exam_code=? GROUP BY topic_subject, topic_point ORDER BY 3 DESC"),
        (True,  True ): ("SELECT topic_subject, topic_point, COUNT(*) FROM questions "
                         "WHERE topic_subject IS NOT NULL AND q_type=? AND exam_code=? GROUP BY topic_subject, topic_point ORDER BY 3 DESC"),
    }
    key = (q_type is not None, exam_code is not None)
    params = [v for v in (q_type, exam_code) if v is not None]
    return conn.execute(_SQL[key], params).fetchall()


# --- seed loader ---
from importlib import resources


def default_db_path() -> Path:
    return Path(__file__).resolve().parent.parent / "data" / "questions.db"


def default_progress_path() -> Path:
    """git-ignored personal-progress DB (attempts/review_state), sibling of the
    shippable bank. Attached as `prog` by connect()."""
    return Path(_progress_path_for(default_db_path()))


def load_seed(conn: sqlite3.Connection) -> int:
    """Load (or reload) the bundled seed data in a single atomic transaction.

    All items are upserted inside one ``with conn:`` block so that a partial
    failure rolls back the entire seed load — preventing a half-written DB.
    Returns the number of seed items processed.
    """
    raw = (resources.files("twexam_mcp.data") / "seed.json").read_text(encoding="utf-8")
    items = json.loads(raw)
    with conn:
        for d in items:
            _upsert(conn, Question.from_dict(d))
    return len(items)


def apply_topic_map(conn: sqlite3.Connection) -> int:
    """Restore 考點 classifications from the bundled topic_map.json.

    questions.db is a rebuildable artifact, so this JSON is the durable source
    of the classification work; re-applying it after any full re-ingest/rebuild
    re-attaches (topic_subject, topic_point) onto questions by qid. Missing qids
    are skipped silently.
    Returns the number of rows updated.
    """
    try:
        raw = (resources.files("twexam_mcp.data") / "topic_map.json").read_text(encoding="utf-8")
    except FileNotFoundError:
        return 0
    mapping = json.loads(raw)
    n = 0
    with conn:
        for qid, t in mapping.items():
            cur = conn.execute(
                "UPDATE questions SET topic_subject=?, topic_point=? WHERE qid=?",
                (t.get("topic_subject"), t.get("topic_point"), qid),
            )
            n += cur.rowcount
    return n


def apply_essay_answers(conn: sqlite3.Connection) -> int:
    """Restore essay model answers (擬答) from the bundled essay_answers.json.

    questions.db is a rebuildable artifact, so this JSON is the durable source
    of the AI-generated 擬答. Run after any full re-ingest/rebuild to re-attach
    model_answer by qid.
    Returns the number of rows updated.
    """
    try:
        raw = (resources.files("twexam_mcp.data") / "essay_answers.json").read_text(encoding="utf-8")
    except FileNotFoundError:
        return 0
    mapping = json.loads(raw)
    n = 0
    with conn:
        for qid, answer in mapping.items():
            cur = conn.execute(
                "UPDATE questions SET model_answer=? WHERE qid=?", (answer, qid),
            )
            n += cur.rowcount
    return n


def retag_all_statutes(conn: sqlite3.Connection) -> dict[str, list[str]]:
    """Recompute every question's statutes from stem + options + model_answer.

    Fixes the ingest-time bug where statutes were tagged from the *stem only*
    (pipeline.ingest_exam), so essays — whose 條號 live in the 擬答, not the
    stem — were left with empty/partial `statutes`, silently breaking
    search_by_statute / get_statute_frequency for the entire essay bank.

    Updates questions.statutes AND rebuilds statute_xref atomically, and
    returns {qid: [statutes]} so callers can persist a bundled statute_map.json.
    """
    from twexam_mcp.ingest import statute_tagger  # local: stdlib-only, no [ingest] extras
    rows = conn.execute("SELECT qid, stem, options, model_answer FROM questions").fetchall()
    result: dict[str, list[str]] = {}
    with conn:
        for r in rows:
            opts = " ".join(json.loads(r["options"] or "[]"))
            text = "\n".join(p for p in (r["stem"], opts, r["model_answer"]) if p)
            sts = statute_tagger.extract_statutes(text)
            conn.execute("UPDATE questions SET statutes=? WHERE qid=?",
                         (json.dumps(sts, ensure_ascii=False), r["qid"]))
            conn.execute("DELETE FROM statute_xref WHERE qid=?", (r["qid"],))
            for s in sts:
                conn.execute("INSERT OR IGNORE INTO statute_xref (statute, qid) VALUES (?,?)",
                             (s, r["qid"]))
            result[r["qid"]] = sts
    return result


def apply_statute_map(conn: sqlite3.Connection) -> int:
    """Restore richer statutes + statute_xref from the bundled statute_map.json.

    questions.db is a rebuildable artifact, so this JSON is the durable source
    of the re-tagging work (retag_all_statutes) across a full rebuild. Mirrors
    apply_essay_answers / apply_topic_map. Missing qids are skipped. Returns
    rows updated.
    """
    try:
        raw = (resources.files("twexam_mcp.data") / "statute_map.json").read_text(encoding="utf-8")
    except FileNotFoundError:
        return 0
    mapping = json.loads(raw)
    n = 0
    with conn:
        for qid, sts in mapping.items():
            cur = conn.execute("UPDATE questions SET statutes=? WHERE qid=?",
                               (json.dumps(sts, ensure_ascii=False), qid))
            if cur.rowcount:
                conn.execute("DELETE FROM statute_xref WHERE qid=?", (qid,))
                for s in sts:
                    conn.execute("INSERT OR IGNORE INTO statute_xref (statute, qid) VALUES (?,?)",
                                 (s, qid))
                n += cur.rowcount
    return n


# ---------------------------------------------------------------------------
# Weak-point engine: spaced-repetition scheduling + mastery analytics
# ---------------------------------------------------------------------------
_LEITNER = [1, 3, 7, 16, 35]  # days between reviews as the streak grows


def _sr_interval(streak: int) -> int:
    """Days until next review after `streak` consecutive correct answers."""
    if streak <= 0:
        return 0
    if streak <= len(_LEITNER):
        return _LEITNER[streak - 1]
    return _LEITNER[-1] * (2 ** (streak - len(_LEITNER)))


def _add_days(iso_day: str, days: int) -> str:
    return (date.fromisoformat(iso_day) + timedelta(days=days)).isoformat()


def record_answer(conn, qid, user_answer=None, self_correct=None, today=None) -> dict:
    """Grade one attempt, log it, and update the spaced-repetition schedule.

    MCQ is auto-graded against questions.answer ('#' 送分 always counts correct).
    Essay is not auto-gradable: pass self_correct (True/False) to schedule it,
    or leave None to log the attempt without affecting the review schedule.
    Returns a result dict with grading + new due date.
    """
    today = today or date.today().isoformat()
    row = conn.execute(
        "SELECT answer, q_type, topic_subject, topic_point FROM questions WHERE qid=?",
        (qid,),
    ).fetchone()
    if row is None:
        raise ValueError(f"unknown qid: {qid}")
    correct_answer, q_type = row["answer"], row["q_type"]
    is_grace = (correct_answer == "#")

    if q_type == "mcq":
        ua = (user_answer or "").strip().upper()
        is_correct = 1 if (is_grace or ua == (correct_answer or "").strip().upper()) else 0
    else:  # essay
        is_correct = None if self_correct is None else (1 if self_correct else 0)

    with conn:
        conn.execute(
            "INSERT INTO prog.attempts (qid, user_answer, is_correct, answered_at) VALUES (?,?,?,?)",
            (qid, user_answer, is_correct, today),
        )
        st = conn.execute(
            "SELECT streak, n_attempts, n_correct FROM prog.review_state WHERE qid=?", (qid,)
        ).fetchone()
        streak = st["streak"] if st else 0
        n_att = (st["n_attempts"] if st else 0) + 1
        n_cor = (st["n_correct"] if st else 0) + (1 if is_correct == 1 else 0)

        if is_correct == 0:
            streak, interval, due = 0, 0, today          # wrong → due now, keep drilling
        elif is_correct == 1:
            streak += 1
            interval = _sr_interval(streak)
            due = _add_days(today, interval)
        else:  # essay, ungraded → log only, leave schedule untouched
            interval = st["streak"] if st else 0          # unused placeholder
            due = st["due_date"] if (st and "due_date" in st.keys()) else None
            interval = 0

        conn.execute(
            """INSERT INTO prog.review_state
                 (qid, last_answer, last_correct, n_attempts, n_correct, streak, interval_days, due_date, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?)
               ON CONFLICT(qid) DO UPDATE SET
                 last_answer=excluded.last_answer, last_correct=excluded.last_correct,
                 n_attempts=excluded.n_attempts, n_correct=excluded.n_correct,
                 streak=excluded.streak, interval_days=excluded.interval_days,
                 due_date=excluded.due_date, updated_at=excluded.updated_at""",
            (qid, user_answer, is_correct, n_att, n_cor, streak, interval, due, today),
        )

    return {
        "qid": qid, "q_type": q_type,
        "your_answer": (user_answer or "").strip().upper() if q_type == "mcq" else user_answer,
        "correct_answer": correct_answer,
        "is_correct": (None if is_correct is None else bool(is_correct)),
        "is_grace": is_grace,
        "topic_subject": row["topic_subject"], "topic_point": row["topic_point"],
        "streak": streak, "due_date": due,
    }


def get_weak_topics(conn, q_type="mcq", min_attempts=1, limit=20) -> list[tuple]:
    """Return (topic_subject, topic_point, attempted, correct, accuracy) rows,
    weakest (lowest accuracy) first. Only topics with >= min_attempts."""
    rows = conn.execute(
        """SELECT q.topic_subject, q.topic_point,
                  SUM(r.n_attempts) AS att, SUM(r.n_correct) AS cor
           FROM prog.review_state r JOIN questions q ON q.qid = r.qid
           WHERE q.q_type = ? AND q.topic_point IS NOT NULL
           GROUP BY q.topic_subject, q.topic_point
           HAVING att >= ?
           ORDER BY (CAST(cor AS REAL) / att) ASC, att DESC
           LIMIT ?""",
        (q_type, min_attempts, limit),
    ).fetchall()
    return [(r[0], r[1], r[2], r[3], round(r[3] / r[2], 3) if r[2] else 0.0) for r in rows]


def get_progress(conn, q_type="mcq", today=None) -> dict:
    """Overall progress snapshot for the weak-point dashboard."""
    today = today or date.today().isoformat()
    agg = conn.execute(
        """SELECT COALESCE(SUM(r.n_attempts),0), COALESCE(SUM(r.n_correct),0),
                  COUNT(*)
           FROM prog.review_state r JOIN questions q ON q.qid=r.qid
           WHERE q.q_type=?""",
        (q_type,),
    ).fetchone()
    attempts, correct, seen = agg[0], agg[1], agg[2]
    due = conn.execute(
        """SELECT COUNT(*) FROM prog.review_state r JOIN questions q ON q.qid=r.qid
           WHERE q.q_type=? AND r.due_date IS NOT NULL AND r.due_date <= ?""",
        (q_type, today),
    ).fetchone()[0]
    total = conn.execute("SELECT COUNT(*) FROM questions WHERE q_type=?", (q_type,)).fetchone()[0]
    return {
        "q_type": q_type,
        "total_questions": total,
        "questions_seen": seen,
        "total_attempts": attempts,
        "total_correct": correct,
        "overall_accuracy": round(correct / attempts, 3) if attempts else None,
        "due_for_review": due,
    }


def practice_weak(conn, n=5, subject=None, q_type="mcq", today=None) -> list[Question]:
    """Draw n questions, prioritising (1) reviews due today, weakest-topic first,
    then (2) unattempted questions from the weakest topics. Falls back to any
    unseen question so a fresh user still gets a full set."""
    today = today or date.today().isoformat()

    # weak-topic ranking (lowest accuracy first); used to order both tiers
    weak = get_weak_topics(conn, q_type=q_type, min_attempts=1, limit=1000)
    weak_order = {tp: i for i, (_ts, tp, *_rest) in enumerate(weak)}

    def _rank(q: Question) -> int:
        return weak_order.get(q.topic_point, 10_000)

    # --- tier 1: due reviews ---
    if subject is None:
        due_rows = conn.execute(
            """SELECT q.* FROM prog.review_state r JOIN questions q ON q.qid=r.qid
               WHERE q.q_type=? AND r.due_date IS NOT NULL AND r.due_date<=?""",
            (q_type, today),
        ).fetchall()
        seen_rows = conn.execute(
            """SELECT q.* FROM questions q WHERE q.q_type=? AND q.qid IN
                 (SELECT qid FROM prog.review_state)""", (q_type,),
        ).fetchall()
        unseen_rows = conn.execute(
            """SELECT q.* FROM questions q WHERE q.q_type=? AND q.qid NOT IN
                 (SELECT qid FROM prog.review_state)""", (q_type,),
        ).fetchall()
    else:
        due_rows = conn.execute(
            """SELECT q.* FROM prog.review_state r JOIN questions q ON q.qid=r.qid
               WHERE q.q_type=? AND q.subject=? AND r.due_date IS NOT NULL AND r.due_date<=?""",
            (q_type, subject, today),
        ).fetchall()
        unseen_rows = conn.execute(
            """SELECT q.* FROM questions q WHERE q.q_type=? AND q.subject=? AND q.qid NOT IN
                 (SELECT qid FROM prog.review_state)""", (q_type, subject),
        ).fetchall()

    out: list[Question] = []
    used: set[str] = set()

    def _take(rows):
        pool = sorted((_row_to_question(r) for r in rows), key=_rank)
        for q in pool:
            if q.qid not in used:
                used.add(q.qid)
                out.append(q)
                if len(out) >= n:
                    return True
        return False

    if _take(due_rows):
        return out[:n]
    if _take(unseen_rows):
        return out[:n]
    return out[:n]


def reset_progress(conn) -> None:
    """Wipe all attempts and review state (start a fresh practice history)."""
    with conn:
        conn.execute("DELETE FROM prog.attempts")
        conn.execute("DELETE FROM prog.review_state")


def set_topic_primer(conn, topic_point, primer) -> None:
    """Upsert the must-know study primer for a 考點."""
    today = date.today().isoformat()
    with conn:
        conn.execute(
            """INSERT INTO topic_notes (topic_point, primer, updated_at) VALUES (?,?,?)
               ON CONFLICT(topic_point) DO UPDATE SET primer=excluded.primer, updated_at=excluded.updated_at""",
            (topic_point, primer, today),
        )


def get_topic_primer(conn, topic_point) -> dict:
    """Fetch the study primer for a 考點 (None if not yet written)."""
    row = conn.execute(
        "SELECT topic_point, primer, updated_at FROM topic_notes WHERE topic_point=?",
        (topic_point,),
    ).fetchone()
    if row is None:
        return {"topic_point": topic_point, "primer": None}
    return {"topic_point": row[0], "primer": row[1], "updated_at": row[2]}


def apply_topic_notes(conn: sqlite3.Connection) -> int:
    """Restore all 考點 primers from the bundled topic_notes.json (the durable
    source; questions.db is a rebuildable artifact)."""
    try:
        raw = (resources.files("twexam_mcp.data") / "topic_notes.json").read_text(encoding="utf-8")
    except FileNotFoundError:
        return 0
    mapping = json.loads(raw)
    today = date.today().isoformat()
    n = 0
    with conn:
        for tp, primer in mapping.items():
            conn.execute(
                """INSERT INTO topic_notes (topic_point, primer, updated_at) VALUES (?,?,?)
                   ON CONFLICT(topic_point) DO UPDATE SET primer=excluded.primer, updated_at=excluded.updated_at""",
                (tp, primer, today),
            )
            n += 1
    return n


def get_readiness(conn, target=0.60, q_type="mcq", min_attempts=2, daily=25) -> dict:
    """Frequency-weighted exam-readiness estimate.

    Honest model, not a guarantee:
      * each 考點 is weighted by how often it appears in the real exam
        (from the knowledge graph) — strong topics you rarely see matter less.
      * a topic's accuracy is used only once it has >= min_attempts; until then
        it falls back to a prior (your overall accuracy, or 0.5 cold-start).
      * `projected_score` = Σ(freq · acc) / Σ(freq) across ALL topics.
      * `coverage` (fraction of the bank actually attempted) gauges how much to
        trust the estimate — low coverage = noisy.
      * `drags` = topics that cost the most points: freq · max(0, target-acc).
      * `backlog` = unseen questions sitting in below-target / unpracticed topics;
        `days_to_cover` = backlog / daily (a COVERAGE pace, not a pass promise).
    Recompute daily; the estimate sharpens as real accuracy data accumulates.
    """
    freq = {r[0]: r[1] for r in conn.execute(
        "SELECT topic_point, COUNT(*) FROM questions "
        "WHERE q_type=? AND topic_point IS NOT NULL GROUP BY topic_point", (q_type,))}
    total_q = sum(freq.values())
    if total_q == 0:
        return {"error": "no classified questions for this q_type"}

    meas = {r[0]: (r[1], r[2], r[3]) for r in conn.execute(
        """SELECT q.topic_point, SUM(r.n_attempts), SUM(r.n_correct), COUNT(DISTINCT r.qid)
           FROM prog.review_state r JOIN questions q ON q.qid=r.qid
           WHERE q.q_type=? AND q.topic_point IS NOT NULL
           GROUP BY q.topic_point""", (q_type,))}

    tot_att = sum(m[0] for m in meas.values())
    tot_cor = sum(m[1] for m in meas.values())
    overall_acc = (tot_cor / tot_att) if tot_att else None
    prior = overall_acc if (overall_acc is not None and tot_att >= 10) else 0.5

    weighted = 0.0
    seen_q = 0
    drags = []
    backlog = 0
    for tp, f in freq.items():
        att, cor, seenq = meas.get(tp, (0, 0, 0))
        seen_q += seenq
        measured = att >= min_attempts
        acc = (cor / att) if measured else prior
        weighted += f * acc
        if acc < target:
            backlog += (f - seenq)            # unseen questions in a weak/unknown topic
            drags.append({
                "topic_point": tp, "exam_freq": f,
                "accuracy": round(cor / att, 3) if att else None,
                "status": "weak" if measured else ("untested" if att == 0 else "low_data"),
                "point_drag": round(f * (target - acc), 2),
            })
    drags.sort(key=lambda d: -d["point_drag"])

    projected = weighted / total_q
    coverage = seen_q / total_q
    if coverage < 0.05:
        confidence = "very_low"
    elif coverage < 0.2:
        confidence = "low"
    elif coverage < 0.5:
        confidence = "medium"
    else:
        confidence = "high"
    band = ("ready" if projected >= target
            else "close" if projected >= target - 0.05 else "not_ready")

    return {
        "q_type": q_type,
        "target": target,
        "projected_score": round(projected, 3),
        "measured_accuracy": round(overall_acc, 3) if overall_acc is not None else None,
        "coverage": round(coverage, 3),
        "confidence": confidence,
        "band": band,
        "topics_total": len(freq),
        "topics_tested": sum(1 for tp in freq if meas.get(tp, (0,))[0] >= min_attempts),
        "backlog_questions": backlog,
        "daily_target": daily,
        "days_to_cover": (backlog + daily - 1) // daily if daily else None,
        "top_drags": drags[:8],
    }
