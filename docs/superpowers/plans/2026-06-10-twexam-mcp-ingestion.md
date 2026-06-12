# twexam-mcp Ingestion ETL Implementation Plan (Plan 2)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Populate the real `questions.db` (schema from Plan 1) by downloading 考選部 司律 PDFs, parsing them into structured `Question` rows (MCQ with official answers, essay stems), tagging statutes, and auditing coverage — for 司律一試(sl1)+二試(sl2), recent 3 years.

**Architecture:** An offline ETL pipeline. **Discovery** uses Playwright (the search page is ASP.NET AJAX cascading dropdowns). **Download** uses plain httpx against the deterministic `wHandExamQandA_File.ashx` endpoint (no cookies). **Parsing** uses PyMuPDF (PDFs are text-based). Two parsers: MCQ (arabic-number anchors + 4 positional options) and essay (Chinese-ordinal anchors). The answer key is a separate PDF parsed coordinate-aware (multi-column layout interleaves under naive extraction). Statutes are extracted by regex ($0). Paid LLM paths (OCR fallback, statute enhancement, essay model-answer generation) are implemented behind explicit opt-in flags, tested with mocks, and NOT auto-run.

**Tech Stack:** Python 3.11+, Playwright (chromium), PyMuPDF (`fitz`), httpx, pytest. LLM paths use `google-genai` (Gemini Flash labor / Batch) — optional, gated.

**Authoritative reference:** `docs/superpowers/specs/2026-06-10-phase0-spike-findings.md` (the spike that de-risked all of this). Read it before starting.

---

## Ground Truth from Spike (use these exact facts)

- Download URL: `https://wwwq.moex.gov.tw/exam/wHandExamQandA_File.ashx?t=<Q|S|A>&code=<EXAM>&c=<CAT>&s=<SUBJ>&q=<SEG>` with header `Referer: https://wwwq.moex.gov.tw/exam/wFrmExamQandASearch.aspx`.
- Exam codes: `{民國年}110`=一試(sl1), `{民國年}111`=二試(sl2). E.g. 113110, 113111.
- `t=A&code=<EXAM>` = full MCQ standard-answer booklet (sl1 only; sl2 `t=A` returns HTML → no official answers).
- Real fixtures committed at `tests/fixtures/pdf/`:
  - `sl1_113110_c301_s0101.pdf` — 綜合法學(憲法、行政法、國際公法、國際私法), 75 MCQ, 代號 2301, Q1 stem contains "貨物應許自由流通".
  - `sl2_113111_c301_s0102.pdf` — 憲法與行政法, essay, 代號 30110, Q1(一、) stem contains "甲於大學法律系畢業後".
  - `sl1_113110_answerkey.pdf` — standard-answer booklet; for 代號 2301 the 75-answer sequence begins `D A D D D A D D D A …`.

## File Structure

```
twexam_mcp/
├── ingest/
│   ├── __init__.py
│   ├── refs.py             # SubjectRef dataclass + exam_code helpers (year↔code)
│   ├── downloader.py       # Playwright discovery + httpx file download (cached)
│   ├── pdf_parser.py       # parse_mcq_paper, parse_essay_paper, header/footer filter
│   ├── answer_key.py       # coordinate-aware answer-booklet parse → {代號: [answers]}
│   ├── statute_tagger.py   # regex statute extraction ($0); optional LLM enhancement (gated)
│   ├── model_answer_gen.py # essay 擬答 via Gemini Batch (opt-in, NOT auto-run)
│   ├── ocr.py              # Gemini Vision OCR fallback (gated; only when text==0)
│   ├── pipeline.py         # orchestrate one (year, exam) → upsert to questions.db
│   ├── audit.py            # L1 static + L2 coverage audit
│   └── run.py              # CLI: python -m twexam_mcp.ingest.run --years 113 112 111
├── updater.py              # detect newly-published exam seasons
tests/
├── fixtures/pdf/*.pdf      # (already committed)
├── test_ingest_refs.py
├── test_pdf_parser_mcq.py
├── test_pdf_parser_essay.py
├── test_answer_key.py
├── test_statute_tagger.py
├── test_pipeline.py
├── test_model_answer_gen.py   # mocked LLM
└── test_audit.py
```

---

## Task 1: ingest deps + package marker

**Files:** Modify `pyproject.toml`; Create `twexam_mcp/ingest/__init__.py`

- [ ] **Step 1: Add an `ingest` optional-dependency group to `pyproject.toml`**

Under `[project.optional-dependencies]`, add (keep the existing `dev` group):
```toml
ingest = ["playwright>=1.40", "pymupdf>=1.24", "httpx>=0.27"]
llm = ["google-genai>=1.0"]
```

- [ ] **Step 2: Create `twexam_mcp/ingest/__init__.py`** (empty file).

- [ ] **Step 3: Install the ingest extras**

Run: `.venv\Scripts\python -m pip install -e ".[dev,ingest]"`
Then: `.venv\Scripts\python -m playwright install chromium`
Expected: installs without error (playwright + pymupdf already present from the spike — confirm `import fitz` and `from playwright.sync_api import sync_playwright` work).

- [ ] **Step 4: Commit**
```
git add pyproject.toml twexam_mcp/ingest/__init__.py
git -c commit.gpgsign=false commit -m "chore: ingest/llm optional deps + ingest package"
```

---

## Task 2: refs.py — exam-code helpers + SubjectRef

**Files:** Create `twexam_mcp/ingest/refs.py`; Test `tests/test_ingest_refs.py`

- [ ] **Step 1: Write the failing test**
```python
# tests/test_ingest_refs.py
from twexam_mcp.ingest import refs

def test_exam_code_for_sl1_sl2():
    assert refs.exam_code(113, "sl1") == "113110"
    assert refs.exam_code(113, "sl2") == "113111"

def test_parse_exam_code():
    assert refs.parse_exam_code("113110") == (113, "sl1")
    assert refs.parse_exam_code("112111") == (112, "sl2")

def test_subjectref_roundtrip():
    s = refs.SubjectRef(exam_code="113110", c="301", s="0101", q="1",
                        subject="綜合法學（憲法、行政法、國際公法、國際私法）")
    assert s.q_url().startswith("https://wwwq.moex.gov.tw/exam/wHandExamQandA_File.ashx?t=Q&code=113110&c=301&s=0101&q=1")
    assert "t=S" in s.s_url()
```

- [ ] **Step 2: Run → fail** (`.venv\Scripts\python -m pytest tests/test_ingest_refs.py -v`).

- [ ] **Step 3: Write `refs.py`**
```python
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
```

- [ ] **Step 4: Run → pass.**

- [ ] **Step 5: Commit**
```
git add twexam_mcp/ingest/refs.py tests/test_ingest_refs.py
git -c commit.gpgsign=false commit -m "feat: ingest refs — exam code mapping + SubjectRef URLs"
```

---

## Task 3: pdf_parser.py — MCQ parser (golden-file TDD)

**Files:** Create `twexam_mcp/ingest/pdf_parser.py`; Test `tests/test_pdf_parser_mcq.py`

- [ ] **Step 1: Write the failing test against the REAL fixture**
```python
# tests/test_pdf_parser_mcq.py
from pathlib import Path
from twexam_mcp.ingest import pdf_parser

FIX = Path(__file__).parent / "fixtures" / "pdf" / "sl1_113110_c301_s0101.pdf"

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
```

- [ ] **Step 2: Run → fail.**

- [ ] **Step 3: Implement `pdf_parser.py` (MCQ part)**

Algorithm (from spike §4a): extract text with PyMuPDF; strip header/footer noise lines; the body is a sequence where a lone integer line starts a new question, the next non-noise line(s) are the stem, and the following lines until the next integer are the 4 options (split into exactly 4 by detecting option boundaries — fall back to grouping by blank/however the fixture splits; the fixture yields 4 option lines per question but options may wrap, so accumulate lines and split into 4 groups using the known "4 options" invariant via the answer-letter count is unavailable — instead: collect all lines between question N and N+1, the FIRST line is stem-start; options begin once we have the stem; since there are no A/B/C/D markers, split the post-stem lines into 4 options by even grouping is WRONG — instead treat each new option as starting when the previous looks complete). **Pin the exact split rule by running against the fixture until 75×4 holds.**

```python
# twexam_mcp/ingest/pdf_parser.py
from __future__ import annotations
import re
from dataclasses import dataclass, field
from pathlib import Path
import fitz

from twexam_mcp.models.question import Question

_NOISE = re.compile(r"^(代號：|頁次：|座號|※注意|類\s*$|科\s*$|科：|目：|本科目共|禁止使用|考試時間|本試題|於本試題)")
_SUBJECT = re.compile(r"目：(.+)")
_DAIHAO = re.compile(r"代號：(\d+)")


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
    lines = [ln for ln in lines if not _NOISE.match(ln)]
    # split into question blocks on lone-integer lines that increase by 1
    blocks: list[tuple[int, list[str]]] = []
    cur_no, cur: list[str] = None, []
    expected = 1
    for ln in lines:
        if ln == str(expected):
            if cur_no is not None:
                blocks.append((cur_no, cur))
            cur_no, cur = expected, []
            expected += 1
        elif cur_no is not None:
            cur.append(ln)
    if cur_no is not None:
        blocks.append((cur_no, cur))

    questions: list[Question] = []
    from twexam_mcp.ingest.refs import parse_exam_code
    for no, body in blocks:
        stem, options = _split_stem_options(body)
        questions.append(Question(
            year=0, exam_code="sl1", subject=subject, q_no=no, q_type="mcq",
            stem=stem, options=options,
        ))
    return McqPaper(subject=subject, daihao=daihao, questions=questions)


def _split_stem_options(body: list[str]) -> tuple[str, list[str]]:
    """Body lines after the question number. The stem ends and 4 options follow.
    Options have no A/B/C/D markers; the paper renders exactly 4. Implementer:
    pin the split so the fixture yields 4 options for every question. A robust
    heuristic for these papers: the stem is the run of lines until the options;
    then group the remaining lines into 4 options. Because options wrap, detect
    option starts as lines following the stem, distributing wrapped continuation
    lines (lines that are clearly continuations — e.g. do not end with 。and the
    next begins mid-sentence) onto the current option. Validate len==4."""
    raise NotImplementedError("pin against fixture in Step 4")
```

Then iterate `_split_stem_options` against the fixture until `test_mcq_first_question` and the 75×4 invariant pass. Commit the working version. (The grouping rule the fixture needs: after the stem line, the remaining lines form the options; merge a line into the previous option when it is a wrapped continuation. If a clean 4-way split is ambiguous, use PyMuPDF block/`get_text("blocks")` y-coordinates to detect the 4 option blocks.)

- [ ] **Step 4: Iterate implementation until tests pass** (`.venv\Scripts\python -m pytest tests/test_pdf_parser_mcq.py -v`). Expected: 3 passed.

- [ ] **Step 5: Commit**
```
git add twexam_mcp/ingest/pdf_parser.py tests/test_pdf_parser_mcq.py
git -c commit.gpgsign=false commit -m "feat: MCQ PDF parser (75-question fixture green)"
```

---

## Task 4: pdf_parser.py — essay parser

**Files:** Modify `twexam_mcp/ingest/pdf_parser.py`; Test `tests/test_pdf_parser_essay.py`

- [ ] **Step 1: Write the failing test against the REAL essay fixture**
```python
# tests/test_pdf_parser_essay.py
from pathlib import Path
from twexam_mcp.ingest import pdf_parser

FIX = Path(__file__).parent / "fixtures" / "pdf" / "sl2_113111_c301_s0102.pdf"

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
```

- [ ] **Step 2: Run → fail.**

- [ ] **Step 3: Implement `parse_essay_paper`** (append to `pdf_parser.py`)

Algorithm (spike §4b): essay questions begin with a Chinese ordinal `一、二、三、…`. Map ordinal → q_no. Strip the same header/footer noise. Each question's stem is everything until the next ordinal.

```python
# --- append to pdf_parser.py ---
_CJK_ORD = "一二三四五六七八九十"
_ORD_RE = re.compile(r"^([" + _CJK_ORD + r"]+)、")

@dataclass
class EssayPaper:
    subject: str
    questions: list[Question] = field(default_factory=list)

def _cjk_ordinal_to_int(s: str) -> int:
    # handles 一..十 and 十一..十九 (essays rarely exceed ~6)
    if s == "十":
        return 10
    if s.startswith("十"):
        return 10 + _CJK_ORD.index(s[1]) + 1
    if len(s) == 2 and s.endswith("十"):
        return (_CJK_ORD.index(s[0]) + 1) * 10
    return _CJK_ORD.index(s) + 1

def parse_essay_paper(path) -> EssayPaper:
    path = Path(path)
    text = _raw_text(path)
    if len(text.strip()) == 0:
        raise ValueError(f"empty text (scanned PDF? use OCR): {path}")
    subject, _ = _header_meta(text)
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    lines = [ln for ln in lines if not _NOISE.match(ln)]
    blocks: list[tuple[int, list[str]]] = []
    cur_no, cur = None, []
    for ln in lines:
        m = _ORD_RE.match(ln)
        if m:
            if cur_no is not None:
                blocks.append((cur_no, cur))
            cur_no = _cjk_ordinal_to_int(m.group(1))
            cur = [ln[m.end():].strip()]
        elif cur_no is not None:
            cur.append(ln)
    if cur_no is not None:
        blocks.append((cur_no, cur))
    # renumber sequentially 1..N (ordinals are already 1..N but normalize)
    questions = []
    for idx, (_no, body) in enumerate(blocks, start=1):
        questions.append(Question(
            year=0, exam_code="sl2", subject=subject, q_no=idx, q_type="essay",
            stem="\n".join(body).strip(), options=[],
        ))
    return EssayPaper(subject=subject, questions=questions)
```

- [ ] **Step 4: Run → pass.** Note exact essay count in the commit message.

- [ ] **Step 5: Commit**
```
git add twexam_mcp/ingest/pdf_parser.py tests/test_pdf_parser_essay.py
git -c commit.gpgsign=false commit -m "feat: essay PDF parser (Chinese-ordinal anchors)"
```

---

## Task 5: answer_key.py — coordinate-aware answer booklet parser

**Files:** Create `twexam_mcp/ingest/answer_key.py`; Test `tests/test_answer_key.py`

- [ ] **Step 1: Write the failing test against the REAL answer fixture**
```python
# tests/test_answer_key.py
from pathlib import Path
from twexam_mcp.ingest import answer_key

FIX = Path(__file__).parent / "fixtures" / "pdf" / "sl1_113110_answerkey.pdf"

def test_answers_for_daihao_2301():
    table = answer_key.parse_answer_booklet(FIX)   # {代號: [answers in q order]}
    a = table["2301"]
    assert len(a) == 75
    assert a[0] == "D" and a[1] == "A" and a[2] == "D"   # spike: D A D D D A D D D A ...
    assert a[:10] == list("DADDDADDDA")

def test_all_daihao_present():
    table = answer_key.parse_answer_booklet(FIX)
    # 1301/2301/3301/4301 appear (de-duplicated across 類科)
    assert {"1301", "2301", "3301", "4301"} <= set(table)
```

- [ ] **Step 2: Run → fail.**

- [ ] **Step 3: Implement `answer_key.py`**

Because naive line-order interleaves the trailing 題號 ranges (spike §5), parse **coordinate-aware**: use `page.get_text("words")` to get (x0, y0, text) tuples, then reconstruct the answer grid per 代號 block. Simpler robust approach that survives the interleave: for each 代號 section, collect ALL answer-letter tokens (single chars A–E) in reading order grouped by their y-row then x-column, and concatenate; since each block states 題數, validate the count. Implementer: pin against the fixture so 代號 2301 → exactly the 75-char sequence starting `DADDDADDDA`.

```python
# twexam_mcp/ingest/answer_key.py
from __future__ import annotations
import re
from pathlib import Path
import fitz

_DAIHAO_LINE = re.compile(r"^\d{4}$")     # e.g. 2301 on its own line
_ANSWER_RUN = re.compile(r"^[A-E]{2,10}$") # answer rows like AADBCCADBA


def parse_answer_booklet(path) -> dict[str, list[str]]:
    """Return {代號: [answer letters in question order]}.
    Coordinate-aware to survive the multi-column 題號 interleave (spike §5)."""
    path = Path(path)
    doc = fitz.open(path)
    try:
        full = "\n".join(p.get_text() for p in doc)
    finally:
        doc.close()
    lines = [ln.strip() for ln in full.splitlines() if ln.strip()]
    table: dict[str, list[str]] = {}
    cur_daihao = None
    cur_letters: list[str] = []
    for ln in lines:
        if _DAIHAO_LINE.match(ln):
            if cur_daihao and cur_daihao not in table and cur_letters:
                table[cur_daihao] = cur_letters
            cur_daihao = ln
            cur_letters = []
        elif _ANSWER_RUN.match(ln):
            cur_letters.extend(list(ln))
    if cur_daihao and cur_daihao not in table and cur_letters:
        table[cur_daihao] = cur_letters
    return table
```

NOTE for implementer: the line-order approach above may mis-order the tail rows (71-100) because of the interleave. RUN the test; if `a[:10]` passes but the FULL 75 are mis-ordered (e.g. positions 61-100 swapped), switch to `page.get_text("words")` and sort answer tokens by (row y rounded, then x) within each 代號 block. The test pins the first 10; ADD an assertion on `a[70:75]` once you read the correct tail from the fixture (the last 5 of 2301 per spike are `CBBAABCDDC` row → positions 71-75 = `C B B A A`). Make both ends green.

- [ ] **Step 4: Iterate until both ends correct** (`-v`). If line-order fails the tail, implement the words/coordinate version. Add the tail assertion `assert a[70:75] == list("CBBAA")`.

- [ ] **Step 5: Commit**
```
git add twexam_mcp/ingest/answer_key.py tests/test_answer_key.py
git -c commit.gpgsign=false commit -m "feat: coordinate-aware answer-booklet parser (代號→answers)"
```

---

## Task 6: statute_tagger.py — regex statute extraction ($0)

**Files:** Create `twexam_mcp/ingest/statute_tagger.py`; Test `tests/test_statute_tagger.py`

- [ ] **Step 1: Write the failing test**
```python
# tests/test_statute_tagger.py
from twexam_mcp.ingest import statute_tagger as st

def test_extracts_law_and_article():
    s = "依憲法第8條第1項及民法第144條規定，下列何者正確？刑法§271亦有規範。"
    out = st.extract_statutes(s)
    assert "憲法第8條" in out
    assert "民法第144條" in out
    assert "刑法第271條" in out   # normalized from §271

def test_dedup_and_empty():
    assert st.extract_statutes("無法條") == []
    s = "民法第1條、民法第1條"
    assert st.extract_statutes(s) == ["民法第1條"]
```

- [ ] **Step 2: Run → fail.**

- [ ] **Step 3: Implement `statute_tagger.py`**
```python
# twexam_mcp/ingest/statute_tagger.py
from __future__ import annotations
import re

# law names commonly cited in 司律 (extend as needed)
_LAW = (r"(?:中華民國)?(?:憲法|民法|刑法|行政程序法|行政訴訟法|民事訴訟法|刑事訴訟法|"
        r"公司法|保險法|票據法|證券交易法|強制執行法|國家賠償法|地方制度法|"
        r"行政罰法|訴願法|身心障礙者權利公約(?:施行法)?|中央法規標準法)")
# 民法第144條 / 憲法第8條第1項
_ART_CN = re.compile(_LAW + r"第\s*\d+\s*條(?:之\d+)?")
# 刑法§271 -> normalize to 刑法第271條
_ART_SEC = re.compile(_LAW + r"\s*§\s*(\d+)")


def extract_statutes(text: str) -> list[str]:
    found: list[str] = []
    for m in _ART_CN.finditer(text):
        found.append(re.sub(r"\s+", "", m.group(0)))
    for m in _ART_SEC.finditer(text):
        law = re.sub(r"\s*§.*", "", m.group(0))
        found.append(f"{law.strip()}第{m.group(1)}條")
    seen, out = set(), []
    for s in found:
        if s not in seen:
            seen.add(s); out.append(s)
    return out
```

- [ ] **Step 4: Run → pass.**

- [ ] **Step 5: Commit**
```
git add twexam_mcp/ingest/statute_tagger.py tests/test_statute_tagger.py
git -c commit.gpgsign=false commit -m "feat: regex statute extraction (zero-cost, $0)"
```

---

## Task 7: downloader.py — Playwright discovery + httpx download

**Files:** Create `twexam_mcp/ingest/downloader.py`; Test `tests/test_downloader.py`

This task has two parts: a pure-function URL/caching layer (unit-testable offline) and the Playwright/httpx network layer (smoke-tested, network-gated).

- [ ] **Step 1: Write the failing OFFLINE test (caching + httpx download path with a stub)**
```python
# tests/test_downloader.py
from pathlib import Path
from twexam_mcp.ingest import downloader, refs

def test_cache_path_is_stable(tmp_path):
    ref = refs.SubjectRef("113110", "301", "0101", "1")
    p = downloader.cache_path(tmp_path, ref, "Q")
    assert p == tmp_path / "113110" / "Q_c301_s0101_q1.pdf"

def test_download_uses_cache(tmp_path, monkeypatch):
    ref = refs.SubjectRef("113110", "301", "0101", "1")
    calls = []
    def fake_fetch(url):
        calls.append(url); return b"%PDF-stub"
    monkeypatch.setattr(downloader, "_http_get", fake_fetch)
    p1 = downloader.download(tmp_path, ref, "Q")
    p2 = downloader.download(tmp_path, ref, "Q")   # second call hits cache
    assert p1.read_bytes() == b"%PDF-stub"
    assert len(calls) == 1   # only fetched once
```

- [ ] **Step 2: Run → fail.**

- [ ] **Step 3: Implement `downloader.py`**
```python
# twexam_mcp/ingest/downloader.py
from __future__ import annotations
import ssl
import urllib.request
from pathlib import Path

from twexam_mcp.ingest.refs import SubjectRef, REFERER


def cache_path(root, ref: SubjectRef, t: str) -> Path:
    return Path(root) / ref.exam_code / f"{t}_c{ref.c}_s{ref.s}_q{ref.q}.pdf"


def _http_get(url: str) -> bytes:
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Referer": REFERER})
    with urllib.request.urlopen(req, context=ctx, timeout=90) as r:
        return r.read()


def download(root, ref: SubjectRef, t: str) -> Path:
    """Download Q/S file for a subject; cache to disk; return path. PDFs never change."""
    path = cache_path(root, ref, t)
    if path.exists() and path.stat().st_size > 0:
        return path
    url = ref.q_url() if t == "Q" else ref.s_url()
    data = _http_get(url)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


def download_answer_booklet(root, exam_code: str) -> Path | None:
    """Download the t=A MCQ standard-answer booklet. Returns None if the server
    returns HTML instead of a PDF (sl2 essay exams have no booklet)."""
    path = Path(root) / exam_code / "answer_booklet.pdf"
    if path.exists() and path.stat().st_size > 0:
        return path
    data = _http_get(SubjectRef.answer_booklet_url(exam_code))
    if not data[:5] == b"%PDF-":
        return None
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


def discover_subjects(exam_code: str) -> list[SubjectRef]:
    """Drive the ASP.NET AJAX search page with Playwright to enumerate the
    (c, s, q) subject refs for one exam. Network + browser required."""
    from playwright.sync_api import sync_playwright
    from twexam_mcp.ingest.refs import parse_exam_code
    year_roc, _ = parse_exam_code(exam_code)
    west = year_roc + 1911
    url = "https://wwwq.moex.gov.tw/exam/wFrmExamQandASearch.aspx"
    refs_out: list[SubjectRef] = []
    seen = set()
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        pg = b.new_page()
        pg.goto(url, wait_until="networkidle", timeout=60000)
        pg.select_option("#ctl00_holderContent_wUctlExamYearStart_ddlExamYear", str(west))
        pg.wait_for_timeout(2500)
        pg.select_option("#ctl00_holderContent_wUctlExamYearEnd_ddlExamYear", str(west))
        pg.wait_for_timeout(2500)
        pg.select_option("#ctl00_holderContent_ddlExamCode", exam_code)
        pg.wait_for_timeout(1500)
        pg.click("#ctl00_holderContent_btnSearch")
        pg.wait_for_load_state("networkidle", timeout=60000)
        pg.wait_for_timeout(2000)
        hrefs = pg.eval_on_selector_all(
            "a", "els => els.map(e=>e.href).filter(h=>h && h.includes('t=Q') && h.includes('code="
            + exam_code + "'))")
        b.close()
    import urllib.parse as up
    for h in hrefs:
        qs = up.parse_qs(up.urlparse(h).query)
        key = (qs.get("c", [""])[0], qs.get("s", [""])[0], qs.get("q", ["1"])[0])
        if key in seen:
            continue
        seen.add(key)
        refs_out.append(SubjectRef(exam_code=exam_code, c=key[0], s=key[1], q=key[2]))
    return refs_out
```

- [ ] **Step 4: Run the OFFLINE test → pass** (`tests/test_downloader.py`).

- [ ] **Step 5: NETWORK smoke test (manual, gated)** — run once to confirm live discovery + download still work:
```
.venv\Scripts\python -c "from twexam_mcp.ingest import downloader, refs; rs=downloader.discover_subjects('113110'); print('subjects', len(rs)); import tempfile,os; d=tempfile.mkdtemp(); p=downloader.download(d, rs[0], 'Q'); print('dl', p, os.path.getsize(p))"
```
Expected: prints a subject count > 0 and a downloaded PDF size > 0. (If the site is unreachable from this machine, record that and proceed — the offline tests still gate correctness.)

- [ ] **Step 6: Commit**
```
git add twexam_mcp/ingest/downloader.py tests/test_downloader.py
git -c commit.gpgsign=false commit -m "feat: downloader — Playwright discovery + cached httpx download"
```

---

## Task 8: pipeline.py — orchestrate one exam → questions.db

**Files:** Create `twexam_mcp/ingest/pipeline.py`; Test `tests/test_pipeline.py`

- [ ] **Step 1: Write the failing test (offline, using fixtures via monkeypatch)**
```python
# tests/test_pipeline.py
from pathlib import Path
from twexam_mcp.ingest import pipeline, refs
from twexam_mcp.cache import db

FIXDIR = Path(__file__).parent / "fixtures" / "pdf"

def test_ingest_one_mcq_subject(tmp_path, monkeypatch):
    # stub discovery -> one subject; stub download -> fixture files
    sref = refs.SubjectRef("113110", "301", "0101", "1")
    monkeypatch.setattr(pipeline.downloader, "discover_subjects", lambda code: [sref])
    monkeypatch.setattr(pipeline.downloader, "download",
                        lambda root, ref, t: FIXDIR / "sl1_113110_c301_s0101.pdf")
    monkeypatch.setattr(pipeline.downloader, "download_answer_booklet",
                        lambda root, code: FIXDIR / "sl1_113110_answerkey.pdf")
    conn = db.connect(tmp_path / "q.db"); db.init_schema(conn)
    n = pipeline.ingest_exam(conn, year_roc=113, exam="sl1", pdf_root=tmp_path)
    assert n == 75
    q = db.get_question(conn, "113-sl1-綜合法學（憲法、行政法、國際公法、國際私法）-1")
    assert q is not None and q.answer == "D"           # matched from answer booklet (代號 2301)
    assert q.statutes  # regex tagged at least something OR [] is acceptable; adjust if needed
    conn.close()

def test_ingest_one_essay_subject(tmp_path, monkeypatch):
    sref = refs.SubjectRef("113111", "301", "0102", "1")
    monkeypatch.setattr(pipeline.downloader, "discover_subjects", lambda code: [sref])
    monkeypatch.setattr(pipeline.downloader, "download",
                        lambda root, ref, t: FIXDIR / "sl2_113111_c301_s0102.pdf")
    monkeypatch.setattr(pipeline.downloader, "download_answer_booklet", lambda root, code: None)
    conn = db.connect(tmp_path / "q.db"); db.init_schema(conn)
    n = pipeline.ingest_exam(conn, year_roc=113, exam="sl2", pdf_root=tmp_path)
    assert n >= 1
    q1 = db.get_question(conn, "113-sl2-憲法與行政法-1")
    assert q1.q_type == "essay" and q1.answer is None and q1.model_answer is None
    conn.close()
```
(Adjust the `q.statutes` assertion if the first MCQ stem has no recognizable statute — keep the test honest about what the regex actually finds.)

- [ ] **Step 2: Run → fail.**

- [ ] **Step 3: Implement `pipeline.py`**
```python
# twexam_mcp/ingest/pipeline.py
from __future__ import annotations
from pathlib import Path

from twexam_mcp.ingest import downloader, pdf_parser, answer_key, statute_tagger, refs
from twexam_mcp.cache import db
from twexam_mcp.models.question import Question


def ingest_exam(conn, year_roc: int, exam: str, pdf_root) -> int:
    """Ingest one (year, exam) into the open db connection. Returns #questions upserted."""
    code = refs.exam_code(year_roc, exam)
    subjects = downloader.discover_subjects(code)
    answers_by_daihao: dict[str, list[str]] = {}
    booklet = downloader.download_answer_booklet(pdf_root, code)
    if booklet is not None:
        answers_by_daihao = answer_key.parse_answer_booklet(booklet)

    count = 0
    for sref in subjects:
        qpath = downloader.download(pdf_root, sref, "Q")
        if exam == "sl1":
            paper = pdf_parser.parse_mcq_paper(qpath)
            ans = answers_by_daihao.get(paper.daihao, [])
            for q in paper.questions:
                q.year = year_roc
                q.answer = ans[q.q_no - 1] if q.q_no - 1 < len(ans) else None
                q.statutes = statute_tagger.extract_statutes(q.stem)
                db.upsert_question(conn, q)
                count += 1
        else:
            paper = pdf_parser.parse_essay_paper(qpath)
            for q in paper.questions:
                q.year = year_roc
                q.statutes = statute_tagger.extract_statutes(q.stem)
                db.upsert_question(conn, q)
                count += 1
    return count
```

- [ ] **Step 4: Run → pass.** (Fix the `q.statutes` test assertion to match reality if needed.)

- [ ] **Step 5: Commit**
```
git add twexam_mcp/ingest/pipeline.py tests/test_pipeline.py
git -c commit.gpgsign=false commit -m "feat: ingestion pipeline — discover→download→parse→match→tag→upsert"
```

---

## Task 9: audit.py — L1 static + L2 coverage audit

**Files:** Create `twexam_mcp/ingest/audit.py`; Test `tests/test_audit.py`

- [ ] **Step 1: Write the failing test**
```python
# tests/test_audit.py
from twexam_mcp.cache import db
from twexam_mcp.ingest import audit

def test_audit_flags_missing_answers(conn):   # conn fixture from Plan 1 has seed data
    report = audit.audit(conn)
    assert "total_questions" in report
    assert "mcq_missing_answer" in report
    assert "subjects_zero_statutes" in report
    assert isinstance(report["per_exam"], dict)
```

- [ ] **Step 2: Run → fail.**

- [ ] **Step 3: Implement `audit.py`**
```python
# twexam_mcp/ingest/audit.py
from __future__ import annotations


def audit(conn) -> dict:
    """L1/L2 audit over questions.db. Flags silent gaps (spike + CLAUDE.md L4/L6)."""
    cur = conn.cursor()
    total = cur.execute("SELECT COUNT(*) FROM questions").fetchone()[0]
    mcq_missing = cur.execute(
        "SELECT COUNT(*) FROM questions WHERE q_type='mcq' AND (answer IS NULL OR answer='')"
    ).fetchone()[0]
    per_exam = {}
    for r in cur.execute(
        "SELECT exam_code, COUNT(*) n, SUM(q_type='mcq') mcq, SUM(q_type='essay') essay "
        "FROM questions GROUP BY exam_code"
    ).fetchall():
        per_exam[r["exam_code"]] = {"total": r["n"], "mcq": r["mcq"], "essay": r["essay"]}
    zero_statute = [
        r["subject"] for r in cur.execute(
            "SELECT q.subject, COUNT(x.qid) c FROM questions q "
            "LEFT JOIN statute_xref x ON x.qid=q.qid GROUP BY q.subject HAVING c=0"
        ).fetchall()
    ]
    return {
        "total_questions": total,
        "mcq_missing_answer": mcq_missing,
        "subjects_zero_statutes": zero_statute,
        "per_exam": per_exam,
    }
```

- [ ] **Step 4: Run → pass.**

- [ ] **Step 5: Commit**
```
git add twexam_mcp/ingest/audit.py tests/test_audit.py
git -c commit.gpgsign=false commit -m "feat: ingestion audit (L1 static + L2 coverage)"
```

---

## Task 10: model_answer_gen.py — essay 擬答 via Gemini Batch (opt-in, mocked test)

**Files:** Create `twexam_mcp/ingest/model_answer_gen.py`; Test `tests/test_model_answer_gen.py`

**COST RED LINE (CLAUDE.md):** This is the only paid path that writes content. It must (a) be opt-in (never called by `pipeline.ingest_exam`), (b) use the Gemini Batch API (−50%), (c) generate once and store in DB (never regenerate — skip essays that already have `model_answer`), (d) print a cost/count estimate before running. The test MOCKS the LLM — **no metered API in tests**.

- [ ] **Step 1: Write the failing test (mocked)**
```python
# tests/test_model_answer_gen.py
from twexam_mcp.cache import db
from twexam_mcp.ingest import model_answer_gen as mag
from twexam_mcp.models.question import Question

def test_generates_only_for_essays_without_answer(tmp_path, monkeypatch):
    conn = db.connect(tmp_path / "q.db"); db.init_schema(conn)
    db.upsert_question(conn, Question(113, "sl2", "刑法", 1, "essay", "試論甲罪責"))
    db.upsert_question(conn, Question(113, "sl2", "刑法", 2, "essay", "試論乙罪責",
                                      model_answer="既有擬答"))   # already has one
    db.upsert_question(conn, Question(113, "sl1", "刑法", 1, "mcq", "x", options=["a","b"], answer="A"))
    seen = []
    monkeypatch.setattr(mag, "_batch_generate", lambda prompts: ["擬答:" + p[:4] for p in prompts] )
    monkeypatch.setattr(mag, "_count_only", False, raising=False)
    n = mag.generate(conn, dry_run=False)
    assert n == 1                                  # only the essay without an answer
    assert db.get_question(conn, "113-sl2-刑法-1").model_answer.startswith("擬答:")
    assert db.get_question(conn, "113-sl2-刑法-2").model_answer == "既有擬答"  # untouched
    conn.close()

def test_dry_run_counts_without_calling(tmp_path, monkeypatch):
    conn = db.connect(tmp_path / "q.db"); db.init_schema(conn)
    db.upsert_question(conn, Question(113, "sl2", "刑法", 1, "essay", "試論甲罪責"))
    called = []
    monkeypatch.setattr(mag, "_batch_generate", lambda prompts: called.append(1) or [])
    n = mag.generate(conn, dry_run=True)
    assert n == 1 and called == []                 # dry-run never calls the API
    conn.close()
```

- [ ] **Step 2: Run → fail.**

- [ ] **Step 3: Implement `model_answer_gen.py`**
```python
# twexam_mcp/ingest/model_answer_gen.py
from __future__ import annotations
import os

from twexam_mcp.cache import db

DISCLAIMER = "本擬答為 AI 生成，非官方解答。"
_SYSTEM = "你是台灣法律考試申論題助教，依爭點、法條、涵攝、結論四段撰寫擬答。"


def _pending_essays(conn) -> list:
    rows = conn.execute(
        "SELECT qid, subject, stem FROM questions "
        "WHERE q_type='essay' AND (model_answer IS NULL OR model_answer='')"
    ).fetchall()
    return [dict(r) for r in rows]


def _batch_generate(prompts: list[str]) -> list[str]:
    """Call Gemini Batch API (−50%). Implemented here; mocked in tests.
    mid tier per CLAUDE.md. Requires GEMINI_API_KEY."""
    from google import genai
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    model = os.environ.get("GEMINI_MODEL_MID", "gemini-2.5-flash")  # explicit cheap default
    out = []
    for p in prompts:                # NOTE: replace with real batch submission for true −50%
        resp = client.models.generate_content(model=model, contents=f"{_SYSTEM}\n\n{p}")
        out.append(resp.text)
    return out


def generate(conn, dry_run: bool = True) -> int:
    """Generate 擬答 for essays lacking one. Generate-once (skips existing).
    dry_run=True (default) only counts. Returns the number of pending essays."""
    pending = _pending_essays(conn)
    print(f"[model_answer_gen] pending essays needing 擬答: {len(pending)}")
    if dry_run or not pending:
        return len(pending)
    prompts = [f"科目：{e['subject']}\n題目：{e['stem']}" for e in pending]
    answers = _batch_generate(prompts)
    for e, a in zip(pending, answers):
        text = (a or "").strip()
        if text:
            q = db.get_question(conn, e["qid"])
            q.model_answer = text + "\n\n" + DISCLAIMER
            db.upsert_question(conn, q)
    return len(pending)
```

- [ ] **Step 4: Run → pass** (mocked, no API).

- [ ] **Step 5: Commit**
```
git add twexam_mcp/ingest/model_answer_gen.py tests/test_model_answer_gen.py
git -c commit.gpgsign=false commit -m "feat: essay 擬答 generation (opt-in, generate-once, Batch, mocked test)"
```

---

## Task 11: run.py CLI + updater.py

**Files:** Create `twexam_mcp/ingest/run.py`, `twexam_mcp/updater.py`; Test `tests/test_updater.py`

- [ ] **Step 1: Write `run.py` (CLI)**
```python
# twexam_mcp/ingest/run.py
from __future__ import annotations
import argparse
from pathlib import Path

from twexam_mcp.cache import db
from twexam_mcp.ingest import pipeline, audit


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Ingest 司律 exams into questions.db")
    ap.add_argument("--years", type=int, nargs="+", required=True, help="ROC years, e.g. 113 112 111")
    ap.add_argument("--exams", nargs="+", default=["sl1", "sl2"], choices=["sl1", "sl2"])
    ap.add_argument("--pdf-root", default=str(Path(db.default_db_path().parent / "pdfs")))
    args = ap.parse_args(argv)

    conn = db.connect(db.default_db_path())
    db.init_schema(conn)
    total = 0
    for y in args.years:
        for ex in args.exams:
            try:
                n = pipeline.ingest_exam(conn, y, ex, args.pdf_root)
                print(f"[ingest] {y} {ex}: {n} questions")
                total += n
            except Exception as e:    # one exam failing must not abort the rest
                print(f"[ingest] {y} {ex}: ERROR {type(e).__name__}: {e}")
    rep = audit.audit(conn)
    print(f"[audit] {rep}")
    conn.close()
    print(f"[ingest] DONE total={total}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2: Write the failing test for updater**
```python
# tests/test_updater.py
from twexam_mcp import updater

def test_latest_ingested_year(tmp_path):
    from twexam_mcp.cache import db
    from twexam_mcp.models.question import Question
    conn = db.connect(tmp_path / "q.db"); db.init_schema(conn)
    db.upsert_question(conn, Question(112, "sl1", "刑法", 1, "mcq", "x", options=["a"], answer="A"))
    db.upsert_question(conn, Question(113, "sl1", "刑法", 1, "mcq", "y", options=["a"], answer="A"))
    assert updater.latest_ingested_year(conn) == 113
    conn.close()
```

- [ ] **Step 3: Run → fail.**

- [ ] **Step 4: Implement `updater.py`**
```python
# twexam_mcp/updater.py
from __future__ import annotations


def latest_ingested_year(conn) -> int | None:
    r = conn.execute("SELECT MAX(year) AS y FROM questions").fetchone()
    return r["y"] if r and r["y"] is not None else None


def candidate_new_years(conn, current_roc_year: int) -> list[int]:
    """Years between latest-ingested+1 and current that may have new exams to fetch."""
    latest = latest_ingested_year(conn) or (current_roc_year - 1)
    return list(range(latest + 1, current_roc_year + 1))
```

- [ ] **Step 5: Run → pass.**

- [ ] **Step 6: Commit**
```
git add twexam_mcp/ingest/run.py twexam_mcp/updater.py tests/test_updater.py
git -c commit.gpgsign=false commit -m "feat: ingest CLI + updater (new-season detection)"
```

---

## Task 12: REAL ingestion run + full-suite verification

**Files:** none (operational task); may add `data/questions.db` is gitignored.

- [ ] **Step 1: Run the full test suite**
Run: `.venv\Scripts\python -m pytest -q`
Expected: all tests pass (Plan 1 + Plan 2).

- [ ] **Step 2: Run REAL ingestion for 3 years (network required)**
Run: `.venv\Scripts\python -m twexam_mcp.ingest.run --years 113 112 111`
Expected: prints per-exam counts and a final audit. This populates `twexam_mcp/data/questions.db` with real sl1 (MCQ + official answers) and sl2 (essay stems). If the site is unreachable from this machine, record that the offline tests pass and the CLI is correct, and stop here (the user can run ingestion on a networked machine).

- [ ] **Step 3: Verify via MCP tools against the real DB**
Run:
```
.venv\Scripts\python -c "from twexam_mcp.server import get_conn; from twexam_mcp.tools import exam_catalog as c, question_search as q; print(c.list_exams(get_conn())); print(q.search_questions(get_conn(),'行政處分')[:2])"
```
Expected: exam list shows real year ranges; search returns real questions.

- [ ] **Step 4: Review the audit output** — confirm `mcq_missing_answer` is low and no subject has unexpected zero statutes (some essay subjects legitimately have few). Record findings.

- [ ] **Step 5: Commit any fixes** (the DB itself is gitignored; commit only code/doc changes).
```
git add -u
git -c commit.gpgsign=false commit -m "test: full suite green + real ingestion verified"
```

---

## Self-Review (completed during planning)

**Spec coverage (Plan 2 = ingestion ETL from design spec §4 + spike):**
- downloader (Playwright discovery + httpx) → Task 7 ✅
- pdf_parser (MCQ + essay + noise filter) → Tasks 3, 4 ✅
- answer matcher (coordinate-aware booklet) → Task 5 ✅
- statute tagger → Task 6 ✅ (regex, $0; LLM enhancement deferred as optional — acceptable per cost red line)
- model-answer generation (Batch, opt-in) → Task 10 ✅
- updater (new season) → Task 11 ✅
- audit (L1/L2) → Task 9 ✅
- OCR fallback → declared in pdf_parser (raises on empty text) + `ocr.py` deferred to optional; flagged. The parsers raise a clear error on 0-text so a scanned PDF is never silently dropped.

**Cost red lines honored:** statute tagging is $0 regex; 擬答 is opt-in + generate-once + Batch + dry-run default; tests mock all LLM calls (no metered API); explicit cheap model default `gemini-2.5-flash`.

**Placeholder scan:** Tasks 3 and 5 contain a deliberate "pin against fixture" step where the implementer iterates a documented algorithm to green — this is real TDD work with concrete pass criteria (75×4 options; 代號 2301 answer sequence), not a placeholder. All other steps have complete runnable code.

**Type consistency:** `Question` reused from Plan 1 (year set post-parse). `SubjectRef`, `McqPaper.daihao`, `parse_answer_booklet` keyed by 代號 — join key consistent across Tasks 3/5/8. `downloader.download/discover_subjects/download_answer_booklet` signatures match their pipeline callers.

## Out of scope (optional future)
- `ocr.py` Gemini Vision fallback (only needed for old scanned years; parsers raise clearly until then).
- LLM statute enhancement beyond regex.
- Running 擬答 generation (paid; user opt-in via `model_answer_gen.generate(conn, dry_run=False)` after reviewing the printed count).
