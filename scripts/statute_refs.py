#!/usr/bin/env python
"""從擬答/考點重點/enrich 文字抽出引用法條 → (法規名, 條號)。

零斷點關鍵：§271 在刑法刑訴底下會混（刑法 vs 刑訴），故
1. 有明確前綴（刑訴§/民訴§/通保法§…）→ 依前綴對應法規（LAW_PREFIX）。
2. 無前綴的裸 §條號 → 依該爭點所屬二試科目之預設法規（SUBJECT_DEFAULT）。
   故我自己寫擬答時，程序法一律加前綴（刑訴§/民訴§/通保法§…），裸 § 才安全落到實體法主法典。
被 refresh_statutes.py（抓取/比對）與 render_atlas.py（顯示）共用。
"""
from __future__ import annotations
import re

# 明確前綴 → 全國法規資料庫正式法規名（長前綴排在短前綴前，regex 才不會被短的先吃掉）
LAW_PREFIX = {
    "民訴": "民事訴訟法", "民法": "民法",
    "刑訴": "刑事訴訟法", "刑法": "中華民國刑法", "刑": "中華民國刑法",
    "通保法": "通訊保障及監察法", "通保": "通訊保障及監察法",
    "家事": "家事事件法",
    "公司法": "公司法", "公司": "公司法",
    "證交法": "證券交易法", "證交": "證券交易法",
    "保險法": "保險法",
    "票據法": "票據法",
    "海商法": "海商法", "海商": "海商法",
    "行政訴訟法": "行政訴訟法", "行訴": "行政訴訟法",
    "行政程序法": "行政程序法", "行程": "行政程序法",
    "行政罰法": "行政罰法",
    "國家賠償法": "國家賠償法", "國賠法": "國家賠償法", "國賠": "國家賠償法",
    "憲法": "中華民國憲法", "憲": "中華民國憲法",
    "強制執行法": "強制執行法", "強執": "強制執行法",
    "勞動基準法": "勞動基準法", "勞基法": "勞動基準法",
    "著作權法": "著作權法", "專利法": "專利法", "商標法": "商標法",
}

# 各二試科目「裸 §」預設主法典（無前綴時落點）；含混者不設、強制要前綴
SUBJECT_DEFAULT = {
    "民法與民事訴訟法": "民法",
    "刑法與刑事訴訟法": "中華民國刑法",
}

# 前綴 alternation（長→短，確保「刑訴」「通保法」不被「刑」「通保」先截斷）
_PREFIX_ALT = "|".join(sorted(LAW_PREFIX, key=len, reverse=True))
# §條號：可選前綴 + § + 數字(可帶 -數字)；後面的「項」(羅馬/中文)不計入條號
_RE_SECTION = re.compile(rf"(?:({_PREFIX_ALT}))?\s*§\s*(\d+(?:-\d+)?)")
# 第N條 形式（避免吃到「第1008號」判例字號：限定以「條」結尾）
_RE_TIAO = re.compile(rf"(?:({_PREFIX_ALT}))?第\s*(\d+(?:-\d+)?)\s*條")


def extract_refs(text: str, default_law: str | None) -> set[tuple[str, str]]:
    """回傳 {(法規名, 條號)}；無前綴的裸條號落到 default_law（None 則略過裸條號）。"""
    text = (text or "").replace("`", "")  # 去反引號/行內碼界，避免前綴與 § 被 `…` 切開漏判
    refs: set[tuple[str, str]] = set()
    for rx in (_RE_SECTION, _RE_TIAO):
        for m in rx.finditer(text or ""):
            prefix, art = m.group(1), m.group(2)
            law = LAW_PREFIX[prefix] if prefix else default_law
            if law:
                refs.add((law, art))
    return refs


def stable_key(law: str, art: str) -> str:
    """statutes.json 的 byte 級穩定鍵。"""
    return f"{law}§{art}"
