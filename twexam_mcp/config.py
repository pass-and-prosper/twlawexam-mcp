# twexam_mcp/config.py
"""Static configuration: exam codes, subjects, source domains, cache TTLs."""

# First vertical slice: 司律一試 + 二試
EXAMS = {
    "sl1": "專門職業及技術人員高等考試律師、司法官考試第一試",
    "sl2": "專門職業及技術人員高等考試律師、司法官考試第二試",
}

# Representative subjects per exam (extended during ingestion).
SUBJECTS = {
    "sl1": ["憲法與行政法", "民法與民事訴訟法", "刑法與刑事訴訟法", "商事法", "公司法、保險法"],
    "sl2": ["憲法與行政法", "國文", "民法", "民事訴訟法", "刑法", "刑事訴訟法", "公司法、保險法、證券交易法"],
}

# Live-source whitelist (used by Plan 2 ingestion; declared here for parity with legal-db).
ALLOWED_DOMAINS = {"wwwq.moex.gov.tw", "wwwc.moex.gov.tw"}

# Cache TTLs in seconds (live fetches only; the question bank itself is offline & permanent).
TTL_NEW_EXAM_CHECK = 7 * 24 * 3600
