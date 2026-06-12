# twexam_mcp/ingest/pdf_parser.py
from __future__ import annotations
import re
from dataclasses import dataclass, field
from pathlib import Path
import fitz

from twexam_mcp.models.question import Question

# Header/footer noise lines to discard.
# Generic patterns that survive any year and both 試:
#   - \d+年(公務人員|專門職業)  → any year, both 公務/專技 exam title lines
#   - 考試第[一二]試             → both 第一試 and 第二試
#   - 各類科                     → kept as-is (already generic)
_NOISE = re.compile(
    r"^(代號：|頁次：|座號|※注意|類\s*$|科\s*$|科：|目：|本科目共|禁止使用|考試時間|本試題|"
    r"於本試題|\d+年(?:公務人員|專門職業)|各類科|考試第[一二]試)"
)
_SUBJECT = re.compile(r"目：(.+)")
_DAIHAO = re.compile(r"代號：(\d+)")

# Stray page-footer code lines: a whole line that is nothing but a 4-5 digit
# number (e.g. "30770", "30910").  These are 試卷頁尾代號 noise that the prefixed
# 代號： filter misses.  Anchored on BOTH ends so genuine in-text numbers (法條號,
# 年份, "10萬元") survive — only a line that is *entirely* such a number is cut.
# (Corpus survey: every isolated 4-5 digit line is a footer code; there are no
# standalone 4-digit lines at all, so this never clips a real 代號 or year.)
_ISOLATED_CODE = re.compile(r"^\d{4,5}$")


def _is_noise(ln: str) -> bool:
    return bool(_NOISE.match(ln) or _ISOLATED_CODE.match(ln))

# Option markers — the PDF uses private-use Unicode chars as A/B/C/D bullets
#  = A,  = B,  = C,  = D
_OPTION_MARKERS = {'', '', '', ''}

# PUA stripping — remove leftover private-use-area characters (U+E000–U+F8FF)
# from any text string.  Option markers (U+E18C–U+E18F) are consumed during
# splitting BEFORE this helper is called, so stripping residual PUA is safe.
_PUA_RE = re.compile(r"[-]")


def _strip_pua(s: str) -> str:
    """Remove all Unicode private-use-area chars (U+E000–U+F8FF) from *s*."""
    return _PUA_RE.sub("", s)


@dataclass
class McqPaper:
    subject: str
    daihao: str
    questions: list[Question] = field(default_factory=list)


def _raw_text(path: Path) -> str:
    doc = fitz.open(path)
    try:
        return "\n".join(p.get_text() for p in doc)
    finally:
        doc.close()


def _header_meta(text: str) -> tuple[str, str]:
    subj = ""
    m = _SUBJECT.search(text)
    if m:
        subj = m.group(1).strip()
        # Remove ALL private-use-area characters (U+E000-U+F8FF) from anywhere in
        # the subject string (e.g. stray U+E129 between law name and bracket).
        # These corrupt the qid primary key and get_exam_paper lookup key.
        subj = re.sub("[-]", "", subj).strip()
    dh = ""
    m = _DAIHAO.search(text)
    if m:
        dh = m.group(1)
    return subj, dh


def parse_mcq_paper(path) -> McqPaper:
    path = Path(path)
    text = _raw_text(path)
    if len(text.strip()) == 0:
        raise ValueError(f"empty text (scanned PDF? use OCR): {path}")
    subject, daihao = _header_meta(text)
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    lines = [ln for ln in lines if not _is_noise(ln)]

    # Split into question blocks: a lone integer matching the next expected q_no
    # starts a new question block.
    blocks: list[tuple[int, list[str]]] = []
    cur_no = None
    cur: list[str] = []
    expected = 1
    for ln in lines:
        if ln == str(expected):
            if cur_no is not None:
                blocks.append((cur_no, cur))
            cur_no = expected
            cur = []
            expected += 1
        elif cur_no is not None:
            cur.append(ln)
    if cur_no is not None:
        blocks.append((cur_no, cur))

    questions: list[Question] = []
    for no, body in blocks:
        stem, options = _split_stem_options(body)
        stem = _strip_pua(stem)
        options = [_strip_pua(opt) for opt in options]
        questions.append(Question(
            year=0, exam_code="sl1", subject=subject, q_no=no, q_type="mcq",
            stem=stem, options=options,
        ))
    return McqPaper(subject=subject, daihao=daihao, questions=questions)


def _split_stem_options(body: list[str]) -> tuple[str, list[str]]:
    """Split body lines (after the question number) into stem + 4 options.

    The key insight from inspecting the fixture: every option begins with one of
    four private-use Unicode characters (U+E18C..U+E18F), which are the A/B/C/D
    bullet glyphs embedded in the PDF font.  Continuation lines (option text that
    wraps to the next line) do NOT start with these characters, so we fold them
    into the previous option.  Stem lines appear before the first option marker.

    A marker may appear ANYWHERE in a line, not just at its start: when two short
    options are laid out side-by-side on one physical row (a two-column layout,
    e.g. 109 憲法行政 Q68), ``get_text()`` flattens that row into a single text
    line and the second option's marker (U+E18D) lands mid-line.  We therefore
    scan every line for all marker positions and split each ``marker..next-marker``
    segment into its own option, instead of only inspecting ``ln[0]``.
    """
    stem_lines: list[str] = []
    options: list[str] = []
    current_option_parts: list[str] = []

    in_options = False

    def _flush_current() -> None:
        if current_option_parts:
            options.append(" ".join(current_option_parts))

    for ln in body:
        marker_positions = [i for i, ch in enumerate(ln) if ch in _OPTION_MARKERS]
        if not marker_positions:
            # No marker on this line: stem (before first option) or a wrapped
            # continuation of the current option.
            if in_options:
                current_option_parts.append(ln)
            else:
                stem_lines.append(ln)
            continue

        # Text before the first marker belongs to the stem (if we haven't entered
        # options yet) or continues the option from the previous line.
        prefix = ln[: marker_positions[0]].strip()
        if prefix:
            if in_options:
                current_option_parts.append(prefix)
            else:
                stem_lines.append(prefix)

        # Each marker on this line starts a fresh option; close the previous one.
        for idx, pos in enumerate(marker_positions):
            _flush_current()
            current_option_parts = []
            end = marker_positions[idx + 1] if idx + 1 < len(marker_positions) else len(ln)
            seg = ln[pos + 1:end].strip()
            current_option_parts = [seg] if seg else []
            in_options = True

    # Flush the last option
    _flush_current()

    stem = " ".join(stem_lines).strip()
    return stem, options


# --- Essay parser ---

_CJK_ORD = "一二三四五六七八九十"
_ORD_RE = re.compile(r"^([" + _CJK_ORD + r"]+)、")

# Header lines (代號：/ 頁次：) anchor the true question left margin.
# We match their x0 to distinguish real question ordinals from indented
# reference-law sub-items (which sit ~30+ pts to the right of the header).
_HDR_LINE_PAT = re.compile(r"^(代號：|頁次：)")

# Tolerance (pts) within which an ordinal's left-edge is considered "at the
# question margin".  Empirically the real question markers sit at x0≈34 while
# all nested reference-law sub-items start at x0≥60, so 20 pts of slop is
# more than enough to distinguish them while surviving minor layout variation.
_QUESTION_MARGIN_TOLERANCE = 20.0


@dataclass
class EssayPaper:
    subject: str
    questions: list[Question] = field(default_factory=list)


def _cjk_ordinal_to_int(s: str) -> int:
    """Convert a CJK ordinal string like '一','二'...'十','十一'...'十九' to int."""
    if s == "十":
        return 10
    if s.startswith("十"):
        return 10 + _CJK_ORD.index(s[1]) + 1
    if len(s) == 2 and s.endswith("十"):
        return (_CJK_ORD.index(s[0]) + 1) * 10
    return _CJK_ORD.index(s) + 1


def _essay_lines_with_x0(path: Path) -> list[tuple[float, str]]:
    """Return (x0, stripped_text) for every non-empty line in the PDF.

    Uses get_text("dict") so we can recover the left-edge x-coordinate of
    each text span / line, needed to distinguish top-level question markers
    (left margin) from indented sub-items inside appended reference laws.
    """
    doc = fitz.open(path)
    result: list[tuple[float, str]] = []
    try:
        for page in doc:
            blocks = page.get_text("dict", flags=fitz.TEXT_PRESERVE_WHITESPACE)["blocks"]
            for block in blocks:
                if block.get("type") != 0:   # 0 = text block
                    continue
                for line in block.get("lines", []):
                    spans = line.get("spans", [])
                    if not spans:
                        continue
                    # Left edge of the line = minimum x0 across all its spans
                    line_x0 = min(sp["bbox"][0] for sp in spans)
                    line_text = "".join(sp["text"] for sp in spans).strip()
                    if line_text:
                        result.append((line_x0, line_text))
    finally:
        doc.close()
    return result


def parse_essay_paper(path) -> EssayPaper:
    path = Path(path)

    # We need the raw text for subject/noise detection (fast path)
    text = _raw_text(path)
    if len(text.strip()) == 0:
        raise ValueError("empty text (scanned PDF? use OCR): " + str(path))
    subject, _ = _header_meta(text)

    # Build the full list of (x0, line_text) pairs BEFORE noise filtering
    # so we can extract the header margin from 代號：/頁次： lines first.
    all_lines_x0 = _essay_lines_with_x0(path)

    # --- Determine header margin ---
    # The left-hand 代號：/頁次： lines appear at x0 ≈ 34 pt.
    # Only take the minimum x0 among those lines so right-side duplicates
    # (which sit at x0 ≈ 498 pt) don't inflate the anchor.
    hdr_x0s = [x for x, ln in all_lines_x0 if _HDR_LINE_PAT.match(ln)]
    # Restrict to the left-side header lines only (< page midpoint, say < 200 pt)
    left_hdr_x0s = [x for x in hdr_x0s if x < 200.0]
    header_margin = min(left_hdr_x0s) if left_hdr_x0s else 34.0

    # Now apply noise filter
    lines_x0 = [(x, ln) for x, ln in all_lines_x0 if not _is_noise(ln)]

    # --- Determine which ordinal lines are main-question boundaries ---
    # An ordinal is a NEW QUESTION only when its x0 is within
    # _QUESTION_MARGIN_TOLERANCE pts of the header_margin.
    # Reference-law sub-items sit ~30+ pts to the right and are folded in.
    blocks: list[tuple[int, list[str]]] = []
    cur_no: int | None = None
    cur: list[str] = []

    for x0, ln in lines_x0:
        m = _ORD_RE.match(ln)
        is_question_boundary = (
            m is not None
            and (x0 - header_margin) <= _QUESTION_MARGIN_TOLERANCE
        )
        if is_question_boundary:
            if cur_no is not None:
                blocks.append((cur_no, cur))
            cur_no = _cjk_ordinal_to_int(m.group(1))
            rest = ln[m.end():].strip()
            cur = [rest] if rest else []
        elif cur_no is not None:
            cur.append(ln)
        # Lines before first detected question boundary are discarded
        # (they are noise / instructions that survived the noise filter).

    if cur_no is not None:
        blocks.append((cur_no, cur))

    # --- Fallback: no margin-anchored ordinals found ---
    # This happens when a paper has no 一、二、 markers at the question level
    # (e.g. sl2_112121 where all ordinals are inside 參考法條 sub-items).
    # Emit the entire body as a single essay question rather than fabricating
    # fragments from the reference-law sub-items.
    if not blocks:
        body_lines = [ln for _x, ln in lines_x0]
        stem = _strip_pua("\n".join(body_lines).strip())
        if stem:
            return EssayPaper(
                subject=subject,
                questions=[
                    Question(
                        year=0, exam_code="sl2", subject=subject, q_no=1,
                        q_type="essay", stem=stem, options=[],
                    )
                ],
            )
        return EssayPaper(subject=subject, questions=[])

    # Renumber sequentially 1..N
    questions = []
    for idx, (_no, body) in enumerate(blocks, start=1):
        questions.append(Question(
            year=0, exam_code="sl2", subject=subject, q_no=idx, q_type="essay",
            stem=_strip_pua("\n".join(body).strip()), options=[],
        ))
    return EssayPaper(subject=subject, questions=questions)
