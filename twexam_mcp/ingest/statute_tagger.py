# twexam_mcp/ingest/statute_tagger.py
"""Extract statute / 釋字 / 憲判字 citations from question text + 擬答.

Used both at ingest time and by db.retag_all_statutes (which re-runs this over
stem + options + model_answer, since essay 條號 live in the 擬答, not the stem).
"""
from __future__ import annotations
import re

# Law names cited in 司律, incl. the abbreviations 擬答 actually use (民訴法 /
# 刑訴法 / 證交法 / 勞基法). Where one name is a prefix of another, the longer
# / more specific form is listed first so the alternation prefers it.
_LAW = (
    r"(?:中華民國)?(?:"
    # procedural (full + common abbrev)
    r"民事訴訟法|民訴法|刑事訴訟法|刑訴法|行政訴訟法|行政程序法|行政執行法|行政罰法|訴願法|"
    r"強制執行法|非訟事件法|家事事件法|提存法|"
    # core
    r"憲法|民法|刑法|"
    # commercial / financial
    r"公司法|證券交易法|證交法|保險法|票據法|銀行法|期貨交易法|企業併購法|"
    # IP / competition
    r"著作權法|商標法|專利法|營業秘密法|公平交易法|"
    # labor / social
    r"勞動基準法|勞基法|工會法|團體協約法|勞資爭議處理法|職業安全衛生法|"
    r"職業災害勞工保護法|勞工職業災害保險及保護法|勞工保險條例|"
    r"性別平等工作法|性別工作平等法|就業服務法|"
    # tax (longer form before its suffix 營業稅法)
    r"所得稅法|稅捐稽徵法|加值型及非加值型營業稅法|營業稅法|遺產及贈與稅法|"
    # maritime
    r"海商法|船員法|"
    # admin / other
    r"國家賠償法|地方制度法|中央法規標準法|土地法|信託法|個人資料保護法|消費者保護法|"
    r"政府採購法|藥事法|食品安全衛生管理法|"
    r"身心障礙者權利公約(?:施行法)?"
    r")"
)

# Abbreviations → canonical name so reverse-lookup keys don't fragment
# (擬答 writes 民訴法 but a user searches 民事訴訟法).
_ALIAS = {
    "民訴法": "民事訴訟法",
    "刑訴法": "刑事訴訟法",
    "證交法": "證券交易法",
    "勞基法": "勞動基準法",
}

# 民法第144條 / 憲法第8條第1項 / 刑法第38條之1
_ART_CN = re.compile(r"(" + _LAW + r")第\s*(\d+)\s*條(?:\s*之\s*(\d+))?")
# 刑法§271 / 證交法§157-1 / 刑訴法§455之12  →  第N條(之M)
_ART_SEC = re.compile(r"(" + _LAW + r")\s*§\s*(\d+)(?:\s*[-之]\s*(\d+))?")
# 釋字第414、577、794號 (compressed enumeration) → 釋字第N號 each
_INTERP = re.compile(r"(?:司法院)?(?:大法官)?釋字第\s*((?:\d+\s*[、,，]\s*)*\d+)\s*號")
# 111年憲判字第3號 / 憲判字第3號 → 憲判字第N號
_CONST = re.compile(r"憲判字第\s*(\d+)\s*號")
# 「刑事訴訟法（下稱本法）」… 之後的裸 §N / 本法第N條 都歸給該法。
# 程序法擬答慣例：先定義本法，後文全用裸 § —— 不解析會整題零標注。
_HONHO = re.compile(r"(" + _LAW + r")\s*[（(](?:下稱|以下簡稱|下簡稱|簡稱)?\s*本法")
_BARE_SEC = re.compile(r"§\s*(\d+)(?:\s*[-之]\s*(\d+))?")
_HONHO_ART = re.compile(r"本法第\s*(\d+)\s*條(?:\s*之\s*(\d+))?")


def _norm(law: str, n: str, sub: str | None) -> str:
    law = re.sub(r"\s+", "", law)
    law = _ALIAS.get(law, law)
    return f"{law}第{n}條之{sub}" if sub else f"{law}第{n}條"


def extract_statutes(text: str) -> list[str]:
    if not text:
        return []
    found: list[str] = []
    explicit: set[tuple[str, str | None]] = set()  # (條號, 之N) already pinned to a real law
    for m in _ART_CN.finditer(text):
        found.append(_norm(m.group(1), m.group(2), m.group(3)))
        explicit.add((m.group(2), m.group(3)))
    for m in _ART_SEC.finditer(text):
        found.append(_norm(m.group(1), m.group(2), m.group(3)))
        explicit.add((m.group(2), m.group(3)))
    # 本法 resolution: once "X法（下稱本法）" is defined, bare §N / 本法第N條
    # in the same text resolve to X. Mask already-attributed law§ first so we
    # don't re-attribute explicit citations (e.g. 刑法§271) to 本法.
    hm = _HONHO.search(text)
    if hm:
        default_law = hm.group(1)
        masked = _ART_SEC.sub(" ", text)
        for m in _BARE_SEC.finditer(masked):
            # anti-collision: a bare §N whose 條號 is already pinned to a concrete
            # law (e.g. 刑法§87) is almost certainly that same cite, not 本法.
            if (m.group(1), m.group(2)) in explicit:
                continue
            found.append(_norm(default_law, m.group(1), m.group(2)))
        for m in _HONHO_ART.finditer(text):  # 本法第N條 is explicit about 本法 — trust it
            found.append(_norm(default_law, m.group(1), m.group(2)))
    for m in _INTERP.finditer(text):
        for num in re.split(r"[、,，]", m.group(1)):
            num = num.strip()
            if num:
                found.append(f"釋字第{num}號")
    for m in _CONST.finditer(text):
        found.append(f"憲判字第{m.group(1)}號")
    seen, out = set(), []
    for s in found:
        if s not in seen:
            seen.add(s)
            out.append(s)
    return out
