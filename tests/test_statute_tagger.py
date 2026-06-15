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
    assert st.extract_statutes("") == []
    s = "民法第1條、民法第1條"
    assert st.extract_statutes(s) == ["民法第1條"]

def test_article_with_sub_number():
    # 第N條之M (Chinese) and §N之M / §N-M (section sign) both normalize the same
    assert "民法第425條之1" in st.extract_statutes("類推適用民法第425條之1規定")
    assert "刑法第38條之1" in st.extract_statutes("沒收依刑法§38之1宣告")
    assert "刑事訴訟法第455條之12" in st.extract_statutes("第三人參與沒收（刑事訴訟法§455之12）")
    assert "證券交易法第157條之1" in st.extract_statutes("內線交易見證交法§157-1")

def test_abbreviation_normalized_to_canonical():
    # 擬答 uses abbreviations; reverse-lookup needs them canonicalized
    out = st.extract_statutes("民訴法第446條、刑訴法第131條、證交法第157條、勞基法第11條")
    assert "民事訴訟法第446條" in out
    assert "刑事訴訟法第131條" in out
    assert "證券交易法第157條" in out
    assert "勞動基準法第11條" in out

def test_newly_covered_laws():
    out = st.extract_statutes("違反藥事法第66條第1項；公司法第200條裁判解任；著作權法第10條")
    assert "藥事法第66條" in out
    assert "公司法第200條" in out
    assert "著作權法第10條" in out

def test_interpretations_including_enumeration():
    # 釋字第414、577、794號 — compressed enumeration must yield all three
    out = st.extract_statutes("商業言論見釋字第414、577、794號；另參釋字第604號。")
    assert "釋字第414號" in out
    assert "釋字第577號" in out
    assert "釋字第794號" in out
    assert "釋字第604號" in out

def test_constitutional_court_ruling():
    assert "憲判字第3號" in st.extract_statutes("依111年憲判字第3號意旨")

def test_honho_resolves_bare_section_citations():
    # procedural answers define 本法 then cite bare §; must attribute to that law
    t = ("刑事訴訟法（下稱本法）§128；附帶搜索§130；另案扣押§152；"
         "第三人沒收本法第455條之12；撤銷緩起訴§253之3。但刑法§271另計。")
    out = st.extract_statutes(t)
    assert "刑事訴訟法第128條" in out
    assert "刑事訴訟法第130條" in out
    assert "刑事訴訟法第455條之12" in out
    assert "刑事訴訟法第253條之3" in out
    assert "刑法第271條" in out          # explicit prefix still wins, not mis-cast to 本法
    assert "刑事訴訟法第271條" not in out  # 刑法§271 must NOT leak to 本法

def test_bare_section_not_misattributed_on_number_collision():
    # 刑法§87 (監護) explicit; a stray bare §87 must NOT also become 刑訴§87 (通緝)
    t = "刑事訴訟法（下稱本法）§128。監護處分依刑法§87，又§87施以監護五年。"
    out = st.extract_statutes(t)
    assert "刑法第87條" in out
    assert "刑事訴訟法第128條" in out
    assert "刑事訴訟法第87條" not in out  # collision guard kills the bad 本法 guess
