# twexam_mcp/ingest/answer_key.py
"""Coordinate-aware parser for the 考選部 MCQ standard-answer booklet (t=A).

The booklet is a multi-column table. Naive PyMuPDF line-order interleaves the
tail columns (e.g. 71-80 appears before 61-70 in the text stream because the
PDF stores the rightmost column first for that range row). We use
page.get_text("words") and sort answer tokens by x-coordinate within each
answer row to reconstruct the correct column order.

Layout per 代號 block (repeats 3× — 司法官 / 律師 / 司法官及律師):
  等級名稱：…
  類科名稱：…
  科目名稱：…
  <代號 e.g. 2301>      ← lone 4-digit line
  每題配分：…
  題數：N題
  題號   01-10  11-20 … 51-60   71-80  61-70  …  (y = header_y)
  答案   AAAA…  BBBB… … ZZZZ…   PPPP…  QQQQ…  …  (y = answer_y)

Strategy:
1. Extract all words with (x0, y0, x1, y1, text) per page.
2. Identify 代號 line (4 consecutive digits alone on a line, i.e. y-band has
   exactly one word that is a 4-digit string).
3. For each 代號 block, find the y-row that contains 'DADDDADDDA'-style strings
   (answer row): words matching ^[A-E]{5,10}$ at the same y0 (±2 pt).
4. Sort those answer words by x0 and concatenate → full answer list.
5. Truncate to the 題數 stated in the block.
6. De-duplicate: first occurrence of each 代號 wins (司法官 variant).
"""
from __future__ import annotations
import re
from pathlib import Path

import fitz

_DAIHAO_PAT = re.compile(r"^\d{4}$")     # lone 4-digit 代號 e.g. "2301"
_ANSWER_PAT = re.compile(r"^[A-E#＃*]{2,}$")  # answer run; # / ＃ = 送分 grade-marker
_QCOUNT_PAT = re.compile(r"題數：(\d+)題")


def _round_y(y: float, precision: float = 2.0) -> float:
    """Bucket y-coordinates so words on the same visual row share the same key."""
    return round(y / precision) * precision


def parse_answer_booklet(path) -> dict[str, list[str]]:
    """Return {代號: [answer letters in question order]}.

    Coordinate-aware: within each 代號 block's answer row, answer tokens are
    sorted by x0 (left→right) so the multi-column tail interleave is corrected.
    De-duplicates by keeping only the first occurrence of each 代號.
    """
    path = Path(path)
    doc = fitz.open(path)
    try:
        # Collect (page_no, x0, y0, text) for every word across all pages
        all_words: list[tuple[int, float, float, str]] = []
        for pno, page in enumerate(doc):
            for w in page.get_text("words"):
                x0, y0, _x1, _y1, word, _b, _l, _wn = w
                all_words.append((pno, x0, y0, word.strip()))
    finally:
        doc.close()

    # --- Pass 1: identify 代號 lines (page, y_bucket) and their positions ---
    # A 代號 line is a word matching _DAIHAO_PAT that sits alone on its y-row
    # (or at most shares the row with nearby structural words like 類科名稱).
    # We group words by (page, y_bucket) then find rows with exactly one word
    # that is a 4-digit string.
    from collections import defaultdict
    rows: dict[tuple[int, float], list[tuple[float, str]]] = defaultdict(list)
    for pno, x0, y0, word in all_words:
        key = (pno, _round_y(y0))
        rows[key].append((x0, word))

    # --- Pass 2: scan for 代號 blocks in page+y order ---
    sorted_row_keys = sorted(rows.keys())  # (page, y_bucket) ascending

    # Build a flat list of (page, y_bucket, [(x0, word)...]) in reading order
    ordered_rows = [(pk[0], pk[1], sorted(rows[pk], key=lambda t: t[0]))
                    for pk in sorted_row_keys]

    # Identify rows that contain a lone 代號 word
    daihao_row_indices: list[int] = []
    for i, (pno, yb, words_in_row) in enumerate(ordered_rows):
        daihao_words = [w for _x, w in words_in_row if _DAIHAO_PAT.match(w)]
        if daihao_words:
            daihao_row_indices.append(i)

    table: dict[str, list[str]] = {}  # de-duplicated result

    # For each 代號, scan forward until the next 代號 (or end) to find:
    #   (a) 題數 — so we know how many answers to expect
    #   (b) the answer row — words all matching [A-E]{2,}
    for start_idx in daihao_row_indices:
        pno_start, yb_start, words_in_daihao_row = ordered_rows[start_idx]
        daihao_words = [w for _x, w in words_in_daihao_row if _DAIHAO_PAT.match(w)]
        if not daihao_words:
            continue
        daihao = daihao_words[0]

        if daihao in table:
            continue  # already captured from first occurrence

        # Find the next 代號 row index (or end of list)
        next_daihao_idx = len(ordered_rows)
        for later_idx in daihao_row_indices:
            if later_idx > start_idx:
                next_daihao_idx = later_idx
                break

        # Scan rows between start and next 代號 for 題數 and answer tokens
        q_count: int | None = None
        answer_rows: list[tuple[float, float, list[tuple[float, str]]]] = []
        # answer_rows: list of (page_no, y_bucket, [(x0, answer_word)])

        for i in range(start_idx, next_daihao_idx):
            _pno, _yb, words_in_row = ordered_rows[i]

            # Check for 題數
            if q_count is None:
                for _x, w in words_in_row:
                    m = _QCOUNT_PAT.search(w)
                    if m:
                        q_count = int(m.group(1))
                        break

            # Check if this row contains only answer tokens (A-E strings)
            # At least one word must match _ANSWER_PAT (len >= 5 to avoid stray)
            answer_words_in_row = [(x0, w) for x0, w in words_in_row
                                   if _ANSWER_PAT.match(w) and len(w) >= 5]
            # The answer row also contains the label '答案' — filter non-answer words
            # and check that the answer-letter words dominate the row
            non_label = [(x0, w) for x0, w in words_in_row
                         if w not in ("答案", "題號") and not re.match(r"^\d+$", w)
                         and not re.match(r"^-$", w)]
            # Only count this as an answer row if ALL non-label words are [A-E]+
            if non_label and all(_ANSWER_PAT.match(w) and len(w) >= 2
                                 for _x, w in non_label):
                answer_rows.append((_pno, _yb, [(x0, w) for x0, w in non_label]))

        # Assemble answers: each answer_row may have multiple tokens (columns).
        # Sort tokens by x0 within each row, then concatenate rows in y order
        # (answer_rows is already in ascending y order from ordered_rows).
        all_tokens: list[str] = []
        for _pno, _yb, tokens in answer_rows:
            # Sort by x0 (left → right = column 1 → last column)
            tokens_sorted = sorted(tokens, key=lambda t: t[0])
            for _x, w in tokens_sorted:
                all_tokens.extend(list(w))

        if all_tokens:
            # Truncate to declared 題數
            if q_count is not None:
                all_tokens = all_tokens[:q_count]
            table[daihao] = all_tokens

    return table
