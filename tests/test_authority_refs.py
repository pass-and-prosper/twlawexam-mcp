# tests/test_authority_refs.py
"""實務字號抽取＋正規化：寫法千變萬化（空白/年度/字/第/號）須收斂成 byte 級穩定鍵，
且不可吃到國際法源/法條等非台灣字號。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from authority_refs import extract_authorities  # noqa: E402


def test_court_citation_variants_normalize_to_same_key():
    # 同一判決不同寫法 → 同一鍵
    for txt in ["最高法院92年度台上字第1886號", "92 台上 1886", "92台上1886"]:
        assert ("法院", "92台上1886") in extract_authorities(txt)


def test_da_fating_and_other_court_chars():
    assert ("法院", "110台上大279") in extract_authorities("110 年度台上大字第 279 號")  # 大法庭
    assert ("法院", "107台非173") in extract_authorities("107 台非 173")               # 台非


def test_shizi_and_xianpan():
    assert ("釋字", "釋字535") in extract_authorities("釋字第535號")
    assert ("憲判", "112憲判8") in extract_authorities("112憲判8")
    assert ("憲判", "111憲判3") in extract_authorities("111年憲判字第3號")


def test_resolution():
    assert ("決議", "106民庭決議13") in extract_authorities("106 年第 13 次民庭")
    assert ("決議", "107刑庭決議1") in extract_authorities("107年第1次刑庭")


def test_excludes_non_taiwan_authorities_and_statutes():
    # 國際法源與法條不是可查驗的台灣字號 → 不抽取
    assert extract_authorities("1982年聯合國海洋法公約（UNCLOS）第121條") == set()
    assert extract_authorities("2016年南海仲裁案") == set()
    assert extract_authorities("民法第242條、刑法§271") == set()


def test_multiple_in_one_string():
    got = extract_authorities("參照 釋字第509號 與 最高法院100年度台上字第1672號")
    assert ("釋字", "釋字509") in got and ("法院", "100台上1672") in got
