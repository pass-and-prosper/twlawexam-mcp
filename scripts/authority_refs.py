#!/usr/bin/env python
"""從擬答／考點重點／enrich／essay_issues.practice 文字抽出「實務見解字號」並正規化。

實務字號比法條更容易過期（判例可能停止適用、釋字被憲判取代、見解經大法庭變更），
但寫法千奇百樣（「100 年度台上字第 1982 號」＝「100台上1982」），故抽取的重點是
**正規化成 byte 級穩定鍵**，去掉空白／年度／字／第／號。被 refresh_authorities.py
（盤點待驗）與（未來）render_atlas（過期標紅）共用；實際向法規庫/憲法法庭查驗由具
taiwan-legal-db 的 agent 執行（與法條同模式——靜態頁不能即時打 API）。

type ∈ {釋字, 憲判, 法院, 決議}；釋字/憲判可用 legal-db get_interpretation 查，
法院字號用 search_judgments，決議需人工/裁判庫對照。
"""
from __future__ import annotations
import re

# 釋字第535號 / 釋字535 / 司法院釋字第535號 → 釋字535
_RE_SHIZI = re.compile(r"釋字\s*第?\s*(\d+)\s*號?")
# 112憲判8 / 112年憲判字第8號 / 憲判字第8號 → (year)憲判(n)
_RE_XIANPAN = re.compile(r"(\d{2,3})?\s*年?\s*憲判\s*字?\s*第?\s*(\d+)\s*號?")
# 100年度台上字第1982號 / 102台上3418 / 110年度台上大字第279號 / 107台非173 → (year)(字別)(n)
# 字別限最高法院系列(台上/抗/非/聲/再，可帶「大」＝大法庭)，避免吃到一般數字
_RE_COURT = re.compile(r"(\d{2,3})\s*年?度?\s*(台(?:上|抗|非|聲|再)大?)\s*字?\s*第?\s*(\d+)\s*號?")
# 106年第13次民庭 / 107年第1次刑庭 / 100年度第13次民事庭會議 → (year)(民/刑)庭決議(n)
_RE_RESOLUTION = re.compile(r"(\d{2,3})\s*年?度?\s*第\s*(\d+)\s*次\s*([民刑])事?庭")


def extract_authorities(text: str) -> set[tuple[str, str]]:
    """回傳 {(type, key)}：正規化後的實務見解字號（去空白/年度/字/第/號）。

    國際法源（UNCLOS、南海仲裁案等）非台灣字號、無從以法規庫查驗 → 不在抽取範圍。
    """
    text = (text or "").replace("`", "")
    out: set[tuple[str, str]] = set()
    for n in _RE_SHIZI.findall(text):
        out.add(("釋字", f"釋字{n}"))
    for y, n in _RE_XIANPAN.findall(text):
        out.add(("憲判", f"{y}憲判{n}" if y else f"憲判{n}"))
    for y, zb, n in _RE_COURT.findall(text):
        out.add(("法院", f"{y}{zb}{n}"))
    for y, n, t in _RE_RESOLUTION.findall(text):
        out.add(("決議", f"{y}{t}庭決議{n}"))
    return out
