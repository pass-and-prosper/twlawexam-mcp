# tests/test_topic_atlas.py
"""build_topic_atlas: combined MCQ+essay stats + 還沒考過 detection over the syllabus."""
from twexam_mcp.cache import db
from twexam_mcp.models.question import Question
from twexam_mcp.tools.exam_map import build_topic_atlas, _all_syllabus_topics


def _seed(conn):
    # 既判力 spans both 一試(mcq) and 二試(essay) — the combine case
    db.upsert_question(conn, Question(
        113, "sl1", "綜合法學（民法、民事訴訟法）", 5, "mcq", "既判力客觀範圍？",
        ["A", "B", "C", "D"], answer="A", topic_subject="民事訴訟法", topic_point="既判力"))
    db.upsert_question(conn, Question(
        114, "sl2", "民法與民事訴訟法", 1, "essay", "論既判力遮斷效。",
        topic_subject="民法與民事訴訟法", topic_point="既判力",
        model_answer="..."))
    # a pure-essay topic
    db.upsert_question(conn, Question(
        112, "sl2", "公司法、保險法、證券交易法", 1, "essay", "董事責任？",
        topic_subject="公司法、保險法與證券交易法", topic_point="董事責任",
        model_answer="..."))


def test_combines_mcq_and_essay_per_topic(conn):
    _seed(conn)
    atlas = build_topic_atlas(conn)
    # find 既判力 anywhere in the sections
    found = None
    for sec in atlas["sections"]:
        for subj in sec["subjects"]:
            for grp in subj["groups"]:
                for t in grp["topics"]:
                    if t["topic"] == "既判力":
                        found = t
    assert found is not None
    assert found["mcq"] == 1 and found["essay"] == 1
    assert found["total"] == 2          # combined
    assert found["last_year"] == 114    # max across both
    assert found["examined"] is True


def test_uncovered_topics_flagged(conn):
    _seed(conn)
    atlas = build_topic_atlas(conn)
    # 留置權 is in the syllabus but seeded with zero questions → 還沒考過
    assert "留置權" in atlas["summary"]["uncovered"]
    assert atlas["summary"]["uncovered_count"] == len(atlas["summary"]["uncovered"])
    # examined + uncovered partition the syllabus
    assert atlas["summary"]["examined"] + atlas["summary"]["uncovered_count"] \
        == atlas["summary"]["total_topics"] == len(_all_syllabus_topics())


def test_examined_topic_not_in_uncovered(conn):
    _seed(conn)
    atlas = build_topic_atlas(conn)
    assert "董事責任" not in atlas["summary"]["uncovered"]
    assert "既判力" not in atlas["summary"]["uncovered"]
