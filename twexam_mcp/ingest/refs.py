# twexam_mcp/ingest/refs.py
from __future__ import annotations
from dataclasses import dataclass

BASE = "https://wwwq.moex.gov.tw/exam/wHandExamQandA_File.ashx"
REFERER = "https://wwwq.moex.gov.tw/exam/wFrmExamQandASearch.aspx"
_SUFFIX = {"sl1": "110", "sl2": "111"}
_REV = {v: k for k, v in _SUFFIX.items()}


def exam_code(year_roc: int, exam: str) -> str:
    """ROC year + sl1/sl2 -> 考選部 6-digit code. e.g. (113,'sl1') -> '113110'."""
    return f"{year_roc:03d}{_SUFFIX[exam]}"


def parse_exam_code(code: str) -> tuple[int, str]:
    """'113110' -> (113, 'sl1'). Raises KeyError if suffix unknown."""
    return int(code[:3]), _REV[code[3:]]


@dataclass
class SubjectRef:
    exam_code: str
    c: str
    s: str
    q: str
    subject: str = ""   # filled from PDF header or result page

    def q_url(self) -> str:
        return f"{BASE}?t=Q&code={self.exam_code}&c={self.c}&s={self.s}&q={self.q}"

    def s_url(self) -> str:
        return f"{BASE}?t=S&code={self.exam_code}&c={self.c}&s={self.s}&q={self.q}"

    @staticmethod
    def answer_booklet_url(exam_code: str) -> str:
        return f"{BASE}?t=A&code={exam_code}"
