# tests/test_statute_tagger.py
from twexam_mcp.ingest import statute_tagger as st

def test_extracts_law_and_article():
    s = "依憲法第8條第1項及民法第144條規定，下列何者正確？刑法§271亦有規範。"
    out = st.extract_statutes(s)
    assert "憲法第8條" in out
    assert "民法第144條" in out
    assert "刑法第271條" in out   # normalized from §271

def test_dedup_and_empty():
    assert st.extract_statutes("無法條") == []
    s = "民法第1條、民法第1條"
    assert st.extract_statutes(s) == ["民法第1條"]
