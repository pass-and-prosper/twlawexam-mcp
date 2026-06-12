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


def discover(year_roc: int, exam: str) -> tuple[str | None, list[SubjectRef]]:
    """Find the 司律 exam code for (year, 'sl1'/'sl2') by dropdown LABEL, then
    enumerate its (c, s, q) subject refs — all in one browser session.

    The 考選部 exam-code suffix is NOT a fixed pattern (113 used 110/111 but
    112/111 used 120/121), so we must match the dropdown label
    ("律師…第一試/第二試") rather than constructing the code. Returns
    (exam_code | None, [SubjectRef]); (None, []) if no 司律 exam that year.
    Network + browser required."""
    from playwright.sync_api import sync_playwright
    west = year_roc + 1911
    want = "第一試" if exam == "sl1" else "第二試"
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
        opts = pg.eval_on_selector_all(
            "#ctl00_holderContent_ddlExamCode option",
            "els => els.map(e=>({code:e.value, label:e.textContent.trim()}))")
        code = None
        for o in opts:
            if "律師" in o["label"] and want in o["label"]:
                code = o["code"]
                break
        if code is None:
            b.close()
            return None, []
        pg.select_option("#ctl00_holderContent_ddlExamCode", code)
        pg.wait_for_timeout(1500)
        pg.click("#ctl00_holderContent_btnSearch")
        pg.wait_for_load_state("networkidle", timeout=60000)
        pg.wait_for_timeout(2000)
        hrefs = pg.eval_on_selector_all(
            "a", "els => els.map(e=>e.href).filter(h=>h && h.includes('t=Q') && h.includes('code="
            + code + "'))")
        b.close()
    import urllib.parse as up
    for h in hrefs:
        qs = up.parse_qs(up.urlparse(h).query)
        key = (qs.get("c", [""])[0], qs.get("s", [""])[0], qs.get("q", ["1"])[0])
        if key in seen:
            continue
        seen.add(key)
        refs_out.append(SubjectRef(exam_code=code, c=key[0], s=key[1], q=key[2]))
    return code, refs_out
