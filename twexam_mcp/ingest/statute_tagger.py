# twexam_mcp/ingest/statute_tagger.py
from __future__ import annotations
import re

# law names commonly cited in 司律 (extend as needed)
_LAW = (r"(?:中華民國)?(?:憲法|民法|刑法|行政程序法|行政訴訟法|民事訴訟法|刑事訴訟法|"
        r"公司法|保險法|票據法|證券交易法|強制執行法|國家賠償法|地方制度法|"
        r"行政罰法|訴願法|身心障礙者權利公約(?:施行法)?|中央法規標準法)")
# 民法第144條 / 憲法第8條第1項
_ART_CN = re.compile(_LAW + r"第\s*\d+\s*條(?:之\d+)?")
# 刑法§271 -> normalize to 刑法第271條
_ART_SEC = re.compile(_LAW + r"\s*§\s*(\d+)")


def extract_statutes(text: str) -> list[str]:
    found: list[str] = []
    for m in _ART_CN.finditer(text):
        found.append(re.sub(r"\s+", "", m.group(0)))
    for m in _ART_SEC.finditer(text):
        law = re.sub(r"\s*§.*", "", m.group(0))
        found.append(f"{law.strip()}第{m.group(1)}條")
    seen, out = set(), []
    for s in found:
        if s not in seen:
            seen.add(s); out.append(s)
    return out
