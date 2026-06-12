# tests/test_tools_statute.py
from twexam_mcp.tools import statute_xref as t

def test_search_by_statute(conn):
    res = t.search_by_statute(conn, "行政程序法§92")
    assert [q["qid"] for q in res] == ["113-sl1-憲法與行政法-2"]

def test_statute_frequency_sorted(conn):
    res = t.get_statute_frequency(conn)
    assert res["items"][0]["count"] >= res["items"][-1]["count"]
    assert res["total"] == 4
