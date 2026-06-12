# tests/test_review.py
"""Weak-point engine: grading, spaced-repetition scheduling, mastery analytics."""
from twexam_mcp.cache import db
from twexam_mcp.models.question import Question
from twexam_mcp.tools import review

Q1 = "113-sl1-憲法與行政法-1"   # answer B
Q2 = "113-sl1-憲法與行政法-2"   # answer B
Q3 = "112-sl1-民法與民事訴訟法-3"  # answer C
ESSAY = "113-sl2-刑法-1"


def _set_topic(conn, qid, sub, point):
    with conn:
        conn.execute("UPDATE questions SET topic_subject=?, topic_point=? WHERE qid=?",
                     (sub, point, qid))


# --- grading ---

def test_correct_mcq_marks_correct_and_schedules(conn):
    r = db.record_answer(conn, Q1, "B", today="2026-01-01")
    assert r["is_correct"] is True
    assert r["streak"] == 1
    assert r["due_date"] == "2026-01-02"   # first interval = 1 day


def test_wrong_mcq_due_today_streak_reset(conn):
    r = db.record_answer(conn, Q1, "A", today="2026-01-01")
    assert r["is_correct"] is False
    assert r["streak"] == 0
    assert r["due_date"] == "2026-01-01"   # wrong → due now, keep drilling


def test_case_insensitive_and_whitespace(conn):
    r = db.record_answer(conn, Q1, "  b ", today="2026-01-01")
    assert r["is_correct"] is True


def test_grace_question_always_correct(conn):
    db.upsert_question(conn, Question(113, "sl1", "憲法與行政法", 9, "mcq",
                                      "送分題", ["A", "B", "C", "D"], answer="#"))
    r = db.record_answer(conn, "113-sl1-憲法與行政法-9", "A", today="2026-01-01")
    assert r["is_grace"] is True
    assert r["is_correct"] is True


# --- spaced repetition intervals ---

def test_streak_intervals_progress(conn):
    db.record_answer(conn, Q1, "B", today="2026-01-01")   # streak1 → +1 → 01-02
    r2 = db.record_answer(conn, Q1, "B", today="2026-01-02")  # streak2 → +3
    assert r2["due_date"] == "2026-01-05"
    r3 = db.record_answer(conn, Q1, "B", today="2026-01-05")  # streak3 → +7
    assert r3["due_date"] == "2026-01-12"


def test_wrong_after_streak_resets(conn):
    db.record_answer(conn, Q1, "B", today="2026-01-01")
    r = db.record_answer(conn, Q1, "A", today="2026-01-02")
    assert r["streak"] == 0 and r["due_date"] == "2026-01-02"


# --- analytics ---

def test_weak_topics_ordered_weakest_first(conn):
    _set_topic(conn, Q1, "憲法", "基本權")
    _set_topic(conn, Q3, "物權", "抵押權")
    # 基本權: 1/2 correct (50%); 抵押權: 1/1 correct (100%)
    db.record_answer(conn, Q1, "A", today="2026-01-01")   # wrong
    db.record_answer(conn, Q1, "B", today="2026-01-02")   # right
    db.record_answer(conn, Q3, "C", today="2026-01-01")   # right
    weak = review.get_weak_topics(conn, q_type="mcq")
    assert weak[0]["topic_point"] == "基本權"      # weakest first
    assert weak[0]["accuracy"] == 0.5
    assert weak[-1]["topic_point"] == "抵押權"


def test_progress_counts(conn):
    db.record_answer(conn, Q1, "B", today="2026-01-01")
    db.record_answer(conn, Q3, "A", today="2026-01-01")   # wrong
    p = review.get_progress(conn, q_type="mcq")
    assert p["total_attempts"] == 2
    assert p["total_correct"] == 1
    assert p["overall_accuracy"] == 0.5
    assert p["questions_seen"] == 2
    assert p["due_for_review"] >= 1   # the wrong one is due today (uses real today)


# --- targeted practice ---

def test_practice_weak_prioritises_due_reviews(conn):
    # Q1 answered wrong → due now; others unseen
    db.record_answer(conn, Q1, "A")   # real today → due today
    drawn = db.practice_weak(conn, n=1, q_type="mcq")
    assert len(drawn) == 1
    assert drawn[0].qid == Q1   # the due review wins over unseen questions


def test_practice_weak_fills_with_unseen(conn):
    out = review.practice_weak(conn, n=2, q_type="mcq", hide_answer=True)
    assert len(out) == 2
    assert "answer" not in out[0]   # hidden


# --- reset ---

def test_reset_progress_clears_all(conn):
    db.record_answer(conn, Q1, "B", today="2026-01-01")
    review.reset_progress(conn)
    p = review.get_progress(conn, q_type="mcq")
    assert p["total_attempts"] == 0
    assert p["questions_seen"] == 0


# --- essay path ---

def test_essay_self_correct_schedules(conn):
    r = db.record_answer(conn, ESSAY, self_correct=True, today="2026-01-01")
    assert r["q_type"] == "essay"
    assert r["is_correct"] is True
    assert r["due_date"] == "2026-01-02"


def test_essay_ungraded_logs_without_schedule(conn):
    r = db.record_answer(conn, ESSAY, today="2026-01-01")
    assert r["is_correct"] is None


# --- readiness estimate ---

def test_readiness_frequency_weighted(conn):
    # give the bank some topic frequencies: Q1/Q2 -> 訴訟要件, Q3 -> 物權
    _set_topic(conn, Q1, "民訴", "訴訟要件")
    _set_topic(conn, Q2, "民訴", "訴訟要件")
    _set_topic(conn, Q3, "物權", "抵押權")
    # answer 訴訟要件 perfectly (2 attempts), 抵押權 untested
    db.record_answer(conn, Q1, "B", today="2026-01-01")
    db.record_answer(conn, Q1, "B", today="2026-01-02")
    r = db.get_readiness(conn, target=0.60, min_attempts=2)
    assert 0.0 <= r["projected_score"] <= 1.0
    assert r["topics_total"] == 2
    assert r["topics_tested"] == 1          # only 訴訟要件 has >= 2 attempts
    # 抵押權 is untested and below target with prior 0.5 → appears as a drag
    drag_topics = {d["topic_point"] for d in r["top_drags"]}
    assert "抵押權" in drag_topics
    assert r["confidence"] in ("very_low", "low", "medium", "high")


def test_readiness_empty_is_cold_start(conn):
    _set_topic(conn, Q1, "民訴", "訴訟要件")
    r = db.get_readiness(conn, target=0.60)
    assert r["coverage"] == 0.0
    assert r["confidence"] == "very_low"
    assert r["measured_accuracy"] is None
