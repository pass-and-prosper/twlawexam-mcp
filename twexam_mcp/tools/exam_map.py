# twexam_mcp/tools/exam_map.py
"""考點地圖：一試/二試科目層級與核心考點。"""
from __future__ import annotations
import sqlite3

_SL1_MAP = [
    {
        "subject": "綜合法學（民法、民事訴訟法）",
        "trial": "sl1",
        "q_count_per_year": 75,
        "sub_subjects": [
            {
                "name": "民法總則",
                "topics": ["法律行為", "意思表示瑕疵", "代理", "時效", "法人"],
            },
            {
                "name": "債篇總論",
                "topics": ["契約成立", "給付不能", "損害賠償", "多數債務人", "保證", "連帶債務"],
            },
            {
                "name": "債篇各論",
                "topics": ["買賣", "租賃", "消費借貸", "委任", "承攬", "旅遊", "合夥"],
            },
            {
                "name": "物權",
                "topics": ["所有權", "占有", "地上權", "抵押權（普通/最高限額）", "質權", "留置權"],
            },
            {
                "name": "親屬",
                "topics": ["婚姻成立與撤銷", "離婚", "夫妻財產制", "親子", "監護"],
            },
            {
                "name": "繼承",
                "topics": ["繼承順序", "特留份", "拋棄繼承", "遺囑", "遺產分割"],
            },
            {
                "name": "民事訴訟法",
                "topics": ["管轄", "訴訟要件", "既判力", "上訴", "再審", "假扣押/假處分"],
            },
        ],
    },
    {
        "subject": "綜合法學（刑法、刑事訴訟法、法律倫理）",
        "trial": "sl1",
        "q_count_per_year": 75,
        "sub_subjects": [
            {
                "name": "刑法總則",
                "topics": ["構成要件", "違法性（阻卻事由）", "罪責", "錯誤論", "未遂", "共犯", "競合"],
            },
            {
                "name": "刑法各論",
                "topics": ["殺人傷害", "財產罪（竊盜/詐欺/侵占/背信）", "公務罪", "性犯罪", "遺棄", "毒品"],
            },
            {
                "name": "刑事訴訟法",
                "topics": ["偵查（搜索/扣押/羈押）", "起訴/不起訴", "審判", "證據法則", "上訴", "再審/非常上訴"],
            },
            {
                "name": "法律倫理",
                "topics": ["律師倫理規範", "利益衝突", "保密義務", "檢察官/法官倫理"],
            },
        ],
    },
    {
        "subject": "綜合法學（憲法、行政法、國際公法、國際私法）",
        "trial": "sl1",
        "q_count_per_year": 75,
        "sub_subjects": [
            {
                "name": "憲法",
                "topics": ["基本權（審查標準）", "平等權", "五院組織", "地方自治", "大法官解釋/憲判字"],
            },
            {
                "name": "行政法",
                "topics": ["行政處分", "行政契約", "行政程序法", "行政罰", "訴願", "行政訴訟"],
            },
            {
                "name": "國際公法",
                "topics": ["條約法", "國家與承認", "國際組織", "國際責任", "外交特權", "海洋法"],
            },
            {
                "name": "國際私法",
                "topics": ["準據法", "管轄", "外國判決承認", "涉外婚姻/繼承"],
            },
        ],
    },
    {
        "subject": "綜合法學（公司法、保險法、票據法、證券交易法、強制執行法）",
        "trial": "sl1",
        "q_count_per_year": 75,
        "sub_subjects": [
            {
                "name": "公司法",
                "topics": ["股份有限公司（董事/監察人/股東會）", "有限公司", "公司治理", "企業併購"],
            },
            {
                "name": "保險法",
                "topics": ["保險契約要件", "告知義務", "保險利益", "代位", "人壽/財產保險"],
            },
            {
                "name": "票據法",
                "topics": ["匯票/本票/支票", "背書", "善意取得", "偽造變造", "到期/追索", "時效"],
            },
            {
                "name": "證券交易法",
                "topics": ["內線交易", "公開收購", "買回股份", "申報/公告義務", "操縱市場"],
            },
            {
                "name": "強制執行法",
                "topics": ["執行名義", "動產/不動產執行", "第三人異議之訴", "分配", "假扣押執行"],
            },
        ],
    },
]

_SL2_MAP = [
    {
        "subject": "海商法與海洋法",
        "trial": "sl2",
        "topics": ["船舶所有人責任限制", "海上貨物運送", "共同海損", "海難救助", "船舶抵押", "聯合國海洋法公約"],
    },
    {
        "subject": "公司法、保險法與證券交易法",
        "trial": "sl2",
        "topics": ["公司重整/清算", "董事責任", "保險代位", "內線交易構成要件", "強制公開收購"],
    },
    {
        "subject": "勞動社會法",
        "trial": "sl2",
        "topics": ["勞動契約", "解僱保護", "集體勞動（工會/團協/爭議）", "勞保/健保", "職業災害"],
    },
    {
        "subject": "智慧財產法",
        "trial": "sl2",
        "topics": ["著作權（保護要件/侵害）", "專利（要件/舉發）", "商標", "營業秘密", "公平交易"],
    },
    {
        "subject": "財稅法",
        "trial": "sl2",
        "topics": ["稅捐稽徵法", "所得稅", "遺贈稅", "行政救濟（復查/訴願/行政訴訟）"],
    },
    {
        "subject": "刑法與刑事訴訟法",
        "trial": "sl2",
        "topics": ["共犯論", "財產犯罪", "偵查不公開", "證據排除法則", "認罪協商"],
    },
    {
        "subject": "國文（作文）",
        "trial": "sl2",
        "topics": ["議論文", "說明文", "法律時事評析"],
    },
    {
        "subject": "民法與民事訴訟法",
        "trial": "sl2",
        "topics": ["物權變動", "契約責任與侵權競合", "訴訟標的", "既判力", "非訟事件"],
    },
    {
        "subject": "憲法與行政法",
        "trial": "sl2",
        "topics": ["基本權審查", "法律保留原則", "行政處分違法效果", "國家賠償"],
    },
]


def get_topic_distribution(conn: sqlite3.Connection, q_type: str | None = None,
                           exam_code: str | None = None) -> list[dict]:
    """考點熱度：各 (子科目, 考點) 的題數，由多到少。可選 q_type / exam_code 篩選。"""
    from twexam_mcp.cache import db
    rows = db.topic_distribution(conn, q_type, exam_code)
    return [{"topic_subject": r[0], "topic_point": r[1], "count": r[2]} for r in rows]


def get_exam_map(conn: sqlite3.Connection, trial: str | None = None) -> dict:
    """
    回傳考試科目考點地圖。
    trial: 'sl1'（一試選擇題）/ 'sl2'（二試申論）/ None（全部）。
    同時附上各科目在題庫中的實際題數。
    """
    # 取各科目實際題數
    rows = conn.execute(
        "SELECT subject, q_type, COUNT(*) FROM questions GROUP BY subject, q_type"
    ).fetchall()
    counts: dict[tuple, int] = {(r[0], r[1]): r[2] for r in rows}

    def _count(subject: str, q_type: str) -> int:
        for key, cnt in counts.items():
            if key[0].startswith(subject[:10]) and key[1] == q_type:
                return cnt
        return 0

    result: dict = {"sl1": [], "sl2": []}

    for item in _SL1_MAP:
        if trial and trial != "sl1":
            continue
        entry = dict(item)
        entry["total_questions"] = _count(item["subject"], "mcq")
        result["sl1"].append(entry)

    for item in _SL2_MAP:
        if trial and trial != "sl2":
            continue
        entry = dict(item)
        entry["total_questions"] = _count(item["subject"], "essay")
        result["sl2"].append(entry)

    if trial == "sl1":
        return {"sl1": result["sl1"]}
    if trial == "sl2":
        return {"sl2": result["sl2"]}
    return result
