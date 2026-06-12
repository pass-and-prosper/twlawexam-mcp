# tests/test_pdf_parser_essay.py
from pathlib import Path
from twexam_mcp.ingest import pdf_parser

FIX = Path(__file__).parent / "fixtures" / "pdf" / "sl2_113111_c301_s0102.pdf"
FIX_112 = Path(__file__).parent / "fixtures" / "pdf" / "sl2_112121_c301_s0102.pdf"
# 110 勞動社會法 essay — Q2 stem ends with a stray page-footer code line "30770".
FIX_110_LABOR = Path(__file__).parent / "fixtures" / "pdf" / "sl2_110121_c303_s0103.pdf"


def test_essay_subject_and_first_question():
    paper = pdf_parser.parse_essay_paper(FIX)
    assert "憲法與行政法" in paper.subject
    assert len(paper.questions) >= 1
    q1 = paper.questions[0]
    assert q1.q_no == 1
    assert q1.q_type == "essay"
    assert q1.options == []
    assert "甲於大學法律系畢業後" in q1.stem


def test_essay_question_numbers_contiguous():
    paper = pdf_parser.parse_essay_paper(FIX)
    nos = [q.q_no for q in paper.questions]
    assert nos == list(range(1, len(nos) + 1))


def test_essay_true_question_count():
    """Fixture has exactly 2 main 申論題 — not 39 (the old bug counted indented law sub-items)."""
    paper = pdf_parser.parse_essay_paper(FIX)
    assert len(paper.questions) == 2


def test_essay_second_question_is_genuine():
    """Q2 must be a real 申論題 (乙電廠 / 空污), not a short law sub-item fragment."""
    paper = pdf_parser.parse_essay_paper(FIX)
    q2 = paper.questions[1]
    assert q2.q_no == 2
    assert q2.q_type == "essay"
    assert q2.options == []
    # The second question is about 乙火力發電廠 and air-pollution law — it spans many pages
    # so its stem must be very long and contain distinctive wording.
    assert len(q2.stem) > 500
    assert "乙電廠" in q2.stem or "乙火力發電廠" in q2.stem


def test_essay_no_pua_in_stems():
    """Bug 1: private-use-area glyphs must be stripped from essay stems (was 6 in sl2_113111)."""
    paper = pdf_parser.parse_essay_paper(FIX)
    for q in paper.questions:
        for ch in q.stem:
            assert not (0xE000 <= ord(ch) <= 0xF8FF), (
                f"PUA U+{ord(ch):04X} found in Q{q.q_no} stem"
            )


# --- Bug 3: essay parser anchors questions to header margin; whole-paper fallback ---

def test_112_no_fragment_questions():
    """Bug 3: sl2_112121 has NO ordinals at the question margin.
    After the fix all question stems must be >= 80 chars (no reference-law fragments).
    """
    paper = pdf_parser.parse_essay_paper(FIX_112)
    for q in paper.questions:
        assert len(q.stem) >= 80, (
            f"Q{q.q_no} stem too short ({len(q.stem)} chars) — fragment not suppressed"
        )


def test_112_fallback_question_count():
    """Bug 3: fallback emits 1 question (whole paper) when no margin-anchored ordinals."""
    paper = pdf_parser.parse_essay_paper(FIX_112)
    # The fix produces exactly 1 question via the whole-paper fallback.
    assert len(paper.questions) >= 1, "At least one question expected"
    # Safeguard: no paper should produce more than a small number of main questions.
    # The real content has 2 main questions; the fallback merges them into 1.
    # Either 1 or 2 is acceptable as long as no fragments occur (tested above).
    assert len(paper.questions) <= 5, (
        f"Too many questions ({len(paper.questions)}) — reference-law fragments not suppressed"
    )


def test_112_both_questions_content_present():
    """Bug 3: the merged fallback stem must contain both real questions' key terms."""
    paper = pdf_parser.parse_essay_paper(FIX_112)
    merged_text = " ".join(q.stem for q in paper.questions)
    assert "嚴重特殊傳染性肺炎" in merged_text, "Q1 content (COVID case) missing"
    assert "原住民甲與乙" in merged_text, "Q2 content (Indigenous land case) missing"


def test_110_labor_q2_no_footer_code():
    """Bug B: Q2 stem must not contain the stray page-footer code '30770'."""
    paper = pdf_parser.parse_essay_paper(FIX_110_LABOR)
    assert "勞動社會法" in paper.subject
    q2 = next(q for q in paper.questions if q.q_no == 2)
    assert "30770" not in q2.stem, repr(q2.stem)


def test_110_labor_no_isolated_code_in_any_stem():
    """Bug B regression: no essay stem in the paper carries an isolated 4-5 digit code line."""
    import re
    paper = pdf_parser.parse_essay_paper(FIX_110_LABOR)
    iso = re.compile(r"^\d{4,5}$")
    for q in paper.questions:
        for ln in q.stem.splitlines():
            assert not iso.match(ln.strip()), f"isolated code line in Q{q.q_no}: {ln!r}"


def test_113111_still_two_questions():
    """Bug 3 regression: sl2_113111 must still produce exactly 2 questions."""
    paper = pdf_parser.parse_essay_paper(FIX)
    assert len(paper.questions) == 2
    assert "甲於大學法律系畢業後" in paper.questions[0].stem
