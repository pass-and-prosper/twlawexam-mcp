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
