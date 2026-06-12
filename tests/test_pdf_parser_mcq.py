# tests/test_pdf_parser_mcq.py
from pathlib import Path
from twexam_mcp.ingest import pdf_parser

FIX = Path(__file__).parent / "fixtures" / "pdf" / "sl1_113110_c301_s0101.pdf"
# 109 憲法行政 paper — Q68 (涉外婚姻 / 死亡宣告) has its A & B options laid out
# side-by-side on one physical row, so B's marker (U+E18D) lands mid-line.
FIX_109 = Path(__file__).parent / "fixtures" / "pdf" / "sl1_109120_c301_s0101.pdf"


def test_mcq_subject_and_count():
    paper = pdf_parser.parse_mcq_paper(FIX)
    assert "綜合法學" in paper.subject
    assert paper.daihao == "2301"          # 代號 (join key to answer booklet)
    assert len(paper.questions) == 75


def test_mcq_first_question():
    paper = pdf_parser.parse_mcq_paper(FIX)
    q1 = paper.questions[0]
    assert q1.q_no == 1
    assert "貨物應許自由流通" in q1.stem
    assert len(q1.options) == 4


def test_mcq_question_numbers_contiguous():
    paper = pdf_parser.parse_mcq_paper(FIX)
    assert [q.q_no for q in paper.questions] == list(range(1, 76))


def test_subject_no_pua_chars():
    paper = pdf_parser.parse_mcq_paper(FIX)
    assert all(0xE000 > ord(c) or ord(c) > 0xF8FF for c in paper.subject)


def test_mcq_q68_two_column_options_split():
    """Bug A: 109 憲法行政 Q68 must yield 4 options.

    Options A and B share one physical row (two-column layout) so B's marker
    U+E18D appears mid-line; the parser must split on it, not only at line start.
    """
    paper = pdf_parser.parse_mcq_paper(FIX_109)
    q68 = next(q for q in paper.questions if q.q_no == 68)
    assert len(q68.options) == 4, q68.options
    # Sanity: the two formerly-merged options are now distinct.
    assert any("此屬應依中華民國法律" in o for o in q68.options)
    assert any("甲、乙在我國均無住居所" in o for o in q68.options)
    # The merge must not leave both halves stuck in one option.
    assert not any(
        "此屬應依中華民國法律" in o and "甲、乙在我國均無住居所" in o
        for o in q68.options
    )


def test_mcq_109_all_questions_four_options():
    """Bug A regression: every MCQ in the 109 憲法行政 paper has exactly 4 options."""
    paper = pdf_parser.parse_mcq_paper(FIX_109)
    assert len(paper.questions) == 75
    bad = [(q.q_no, len(q.options)) for q in paper.questions if len(q.options) != 4]
    assert bad == [], f"questions without 4 options: {bad}"


def test_mcq_no_pua_in_stems_or_options():
    """Bug 1: private-use-area glyphs must be stripped from stems and options."""
    paper = pdf_parser.parse_mcq_paper(FIX)
    for q in paper.questions:
        for ch in q.stem:
            assert not (0xE000 <= ord(ch) <= 0xF8FF), (
                f"PUA U+{ord(ch):04X} found in Q{q.q_no} stem"
            )
        for opt in q.options:
            for ch in opt:
                assert not (0xE000 <= ord(ch) <= 0xF8FF), (
                    f"PUA U+{ord(ch):04X} found in Q{q.q_no} option"
                )
