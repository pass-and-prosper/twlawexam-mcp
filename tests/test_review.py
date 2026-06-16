# tests/test_review.py
"""Weak-point engine: grading, spaced-repetition scheduling, mastery analytics."""
import json

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


# --- 申論批改評分表 (get_grading_rubric) ---

def _seed_essay_with_issue(tmp_path):
    c = db.connect(tmp_path / "q.db")
    db.init_schema(c)
    db.upsert_question(c, Question(
        112, "sl2", "民法與民事訴訟法", 1, "essay", "甲對乙起訴，請求移轉A地……",
        topic_subject="民法與民事訴訟法", topic_point="訴訟標的",
        model_answer="**擬答**：本案應為對待給付判決……"))
    qid = "112-sl2-民法與民事訴訟法-1"
    c.execute("INSERT INTO essay_issues(qid,issue_no,issue,doctrines,practice,topic_subject) "
              "VALUES(?,?,?,?,?,?)", (qid, 1, "形成性給付判決得否宣告假執行",
              '["形成判決不得假執行說","給付判決得假執行說"]', '["民訴§389","民訴§390"]',
              "民法與民事訴訟法"))
    c.execute("INSERT INTO issue_primers(issue,data,updated_at) VALUES(?,?,?)",
              ("形成性給付判決得否宣告假執行",
               json.dumps({"signals": "## 🔍 辨識訊號\n**抗辯具形成訴訟性質**＝引爆點",
                           "prereq": "## 📐 前置觀念\n訴訟三類型", "primer": "## 考點重點"},
                          ensure_ascii=False), "2026-01-01"))
    c.commit()
    return c, qid


def test_grading_rubric_assembles_checklist(tmp_path):
    # 批改評分表：每個爭點掛上 學說/實務 + 辨識訊號/前置觀念，並帶滿分擬答與五維準則
    c, qid = _seed_essay_with_issue(tmp_path)
    r = review.get_grading_rubric(c, qid)
    assert r["qid"] == qid
    assert len(r["issues"]) == 1
    it = r["issues"][0]
    assert it["doctrines"] == ["形成判決不得假執行說", "給付判決得假執行說"]
    assert it["practice"] == ["民訴§389", "民訴§390"]
    assert "辨識訊號" in it["signals"] and "前置觀念" in it["prereq"]   # 爭點重點包掛上
    assert r["model_answer"].startswith("**擬答")
    assert len(r["rubric"]) == 5
    c.close()


def test_grading_rubric_rejects_mcq(tmp_path):
    # 選擇題沒有申論批改評分表
    c = db.connect(tmp_path / "q.db")
    db.init_schema(c)
    db.upsert_question(c, Question(
        113, "sl1", "民法", 9, "mcq", "選擇題？", ["甲", "乙", "丙", "丁"],
        answer="A", topic_subject="民法", topic_point="法律行為"))
    c.commit()
    assert review.get_grading_rubric(c, "113-sl1-民法-9")["error"] == "not_an_essay"
    c.close()


# --- 讀書計畫引擎 (get_study_plan) ---

def test_study_plan_phases_cover_all_days(conn):
    # 分相日程：天數加總＝剩餘天數、第一相是掃弱點、帶今日該做與差距
    _set_topic(conn, Q1, "民訴", "訴訟要件")
    p = db.get_study_plan(conn, 30, target=0.60)
    assert p["days_remaining"] == 30
    assert sum(ph["days"] for ph in p["phases"]) == 30        # 各相天數加總＝總天數
    assert p["phases"][0]["phase"].startswith("①")           # 第一相＝掃弱點
    assert "drill" in p["today_focus"]
    assert 0.0 <= p["gap_to_target"] <= 1.0


def test_study_plan_short_timeline_single_sprint(conn):
    # 時間極短（≤2 天）→ 收斂成單一衝刺相
    _set_topic(conn, Q1, "民訴", "訴訟要件")
    p = db.get_study_plan(conn, 2)
    assert len(p["phases"]) == 1
    assert p["phases"][0]["days"] == 2


# --- 錯誤類型診斷 (get_error_diagnosis) ---

def test_error_diagnosis_surfaces_repeated_wrong_pick(conn):
    # Q1 正解 B；學生兩次都選 A（錯）→ 診斷標出反覆選的錯選項＋系統性考點
    _set_topic(conn, Q1, "民訴", "時效")
    db.record_answer(conn, Q1, "A", today="2026-01-01")
    db.record_answer(conn, Q1, "A", today="2026-01-02")
    d = db.get_error_diagnosis(conn, q_type="mcq")
    assert d["n_wrong_questions"] == 1
    err = d["errors"][0]
    assert err["qid"] == Q1 and err["wrong_times"] == 2      # 反覆錯＝系統性
    assert err["your_pick"] == "A" and err["correct"] == "B"
    assert d["systematic_topics"][0]["topic_point"] == "時效"


def test_error_diagnosis_excludes_correct_answers(conn):
    _set_topic(conn, Q1, "民訴", "時效")
    db.record_answer(conn, Q1, "B", today="2026-01-01")      # 答對
    assert db.get_error_diagnosis(conn)["n_wrong_questions"] == 0
