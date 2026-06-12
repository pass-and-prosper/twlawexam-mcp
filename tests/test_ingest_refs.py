from twexam_mcp.ingest import refs

def test_exam_code_for_sl1_sl2():
    assert refs.exam_code(113, "sl1") == "113110"
    assert refs.exam_code(113, "sl2") == "113111"

def test_parse_exam_code():
    assert refs.parse_exam_code("113110") == (113, "sl1")
    assert refs.parse_exam_code("112111") == (112, "sl2")

def test_subjectref_roundtrip():
    s = refs.SubjectRef(exam_code="113110", c="301", s="0101", q="1",
                        subject="綜合法學（憲法、行政法、國際公法、國際私法）")
    assert s.q_url().startswith("https://wwwq.moex.gov.tw/exam/wHandExamQandA_File.ashx?t=Q&code=113110&c=301&s=0101&q=1")
    assert "t=S" in s.s_url()
