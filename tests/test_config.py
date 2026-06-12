from twexam_mcp import config

def test_exam_codes_cover_first_slice():
    assert config.EXAMS["sl1"] == "專門職業及技術人員高等考試律師、司法官考試第一試"
    assert config.EXAMS["sl2"] == "專門職業及技術人員高等考試律師、司法官考試第二試"

def test_subjects_nonempty():
    assert "憲法與行政法" in config.SUBJECTS["sl1"]
    assert isinstance(config.SUBJECTS["sl2"], list)

def test_moex_domain_whitelisted():
    assert "wwwq.moex.gov.tw" in config.ALLOWED_DOMAINS
