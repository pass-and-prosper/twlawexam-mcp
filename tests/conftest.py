# tests/conftest.py
import pytest
from twexam_mcp.cache import db
from twexam_mcp.models.question import Question

SAMPLE = [
    Question(113, "sl1", "憲法與行政法", 1, "mcq",
             "關於法律保留原則，下列敘述何者正確？",
             ["A 僅適用刑罰", "B 涉及人民權利義務應有法律依據", "C 不拘束行政", "D 僅學說"],
             answer="B", statutes=["中央法規標準法§5"]),
    Question(113, "sl1", "憲法與行政法", 2, "mcq",
             "行政處分之構成要件效力，下列何者正確？",
             ["A 無拘束力", "B 他機關應尊重", "C 得任意推翻", "D 僅及於相對人"],
             answer="B", statutes=["行政程序法§92"]),
    Question(113, "sl2", "刑法", 1, "essay",
             "甲基於殺人故意對乙開槍，試論甲之罪責。",
             statutes=["刑法§271"],
             model_answer="一、甲成立刑法第271條第1項殺人既遂罪。(AI 擬答示意)"),
    Question(112, "sl1", "民法與民事訴訟法", 3, "mcq",
             "關於消滅時效，下列何者正確？",
             ["A 期間不得約定", "B 完成後債權消滅", "C 完成後債務人得拒絕給付", "D 法院應依職權"],
             answer="C", statutes=["民法§144"]),
]

@pytest.fixture
def conn(tmp_path):
    c = db.connect(tmp_path / "t.db")
    db.init_schema(c)
    for q in SAMPLE:
        db.upsert_question(c, q)
    yield c
    c.close()
