# twexam_mcp/models/question.py
from __future__ import annotations
from dataclasses import dataclass, field, asdict


@dataclass
class Question:
    year: int                 # 民國年
    exam_code: str            # "sl1" | "sl2" (see config.EXAMS)
    subject: str              # 科目名稱
    q_no: int                 # 題號
    q_type: str               # "essay" | "mcq"
    stem: str                 # 題幹
    options: list[str] = field(default_factory=list)   # mcq 選項；essay 為空
    answer: str | None = None                          # mcq 標準答案 (e.g. "B")；essay 為 None
    statutes: list[str] = field(default_factory=list)  # 引用法條
    model_answer: str | None = None                    # essay AI 擬答；mcq 為 None
    topic_subject: str | None = None                   # 分類後子科目（如「物權」）
    topic_point: str | None = None                     # 分類後考點（如「抵押權（普通/最高限額）」）

    @property
    def qid(self) -> str:
        return f"{self.year}-{self.exam_code}-{self.subject}-{self.q_no}"

    def to_dict(self) -> dict:
        d = asdict(self)
        d["qid"] = self.qid
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Question":
        return cls(
            year=d["year"], exam_code=d["exam_code"], subject=d["subject"],
            q_no=d["q_no"], q_type=d["q_type"], stem=d["stem"],
            options=list(d.get("options") or []),
            answer=d.get("answer"),
            statutes=list(d.get("statutes") or []),
            model_answer=d.get("model_answer"),
            topic_subject=d.get("topic_subject"),
            topic_point=d.get("topic_point"),
        )
