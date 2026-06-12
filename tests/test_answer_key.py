# tests/test_answer_key.py
from pathlib import Path
from twexam_mcp.ingest import answer_key

FIX = Path(__file__).parent / "fixtures" / "pdf" / "sl1_113110_answerkey.pdf"
FIX_111 = Path(__file__).parent / "fixtures" / "pdf" / "sl1_111120_answerkey.pdf"


def test_answers_for_daihao_2301():
    table = answer_key.parse_answer_booklet(FIX)   # {代號: [answers in q order]}
    a = table["2301"]
    assert len(a) == 75
    # First 10 from spike (ground-truth)
    assert a[0] == "D" and a[1] == "A" and a[2] == "D"
    assert a[:10] == list("DADDDADDDA")
    # Tail: Q71-75 verified by coordinate sort of fixture words
    # coordinate dump shows: col 61-70 (x≈750) = CBBAABCDDC, col 71-80 (x≈859) = ABCCA
    # so Q71-75 = first 5 of ABCCA = A B C C A
    assert a[70:75] == list("ABCCA")


def test_all_daihao_present():
    table = answer_key.parse_answer_booklet(FIX)
    # 1301/2301/3301/4301 appear (de-duplicated across 類科)
    assert {"1301", "2301", "3301", "4301"} <= set(table)


# --- Bug 2: # grade-marker (送分) must not drop the entire 代號 block ---

def test_111_grade_marker_daihao_2301_present():
    """Bug 2: sl1_111120 has Q50 marked # (送分); 2301 must still appear."""
    table = answer_key.parse_answer_booklet(FIX_111)
    assert "2301" in table, "2301 must not be dropped when an answer row contains #"


def test_111_grade_marker_length():
    """2301 in the 111 booklet must have exactly 75 answers (題數 = 75)."""
    table = answer_key.parse_answer_booklet(FIX_111)
    a = table["2301"]
    assert len(a) == 75


def test_111_grade_marker_index():
    """Q50 (0-indexed 49) for 2301 in the 111 booklet is the 送分 marker '#'."""
    table = answer_key.parse_answer_booklet(FIX_111)
    a = table["2301"]
    # Coordinate dump: x0=533 token 'DDBACDCAB#' covers columns 41-50.
    # Index within that token: D=41,D=42,B=43,A=44,C=45,D=46,C=47,A=48,B=49,#=50
    # So Q50 is at 0-indexed position 49.
    assert a[49] == "#", f"Expected '#' at index 49 (Q50), got {a[49]!r}"


def test_111_all_daihao_present():
    """All four 代號 blocks must be recovered from the 111 booklet."""
    table = answer_key.parse_answer_booklet(FIX_111)
    assert {"1301", "2301", "3301", "4301"} <= set(table)
