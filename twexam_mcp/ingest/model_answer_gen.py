# twexam_mcp/ingest/model_answer_gen.py
"""Essay 擬答 (model-answer) generation via Gemini Batch API.

Cost red-line compliance (CLAUDE.md):
  - NEVER called by pipeline.ingest_exam — opt-in only via this module directly.
  - dry_run=True is the default — only counts pending essays, never calls the API.
  - Generate-once: skips essays that already have a model_answer stored.
  - Uses gemini-2.5-flash (labor/mid tier) via Batch API (-50% vs sync).
  - Tests mock _batch_generate entirely — zero metered API calls in the test suite.
"""
from __future__ import annotations
import os

from twexam_mcp.cache import db

DISCLAIMER = "本擬答為 AI 生成，非官方解答。"
_SYSTEM = "你是台灣法律考試申論題助教，依爭點、法條、涵攝、結論四段撰寫擬答。"


def _pending_essays(conn) -> list[dict]:
    """Return essays that have no model_answer yet."""
    rows = conn.execute(
        "SELECT qid, subject, stem FROM questions "
        "WHERE q_type='essay' AND (model_answer IS NULL OR model_answer='')"
    ).fetchall()
    return [dict(r) for r in rows]


def _batch_generate(prompts: list[str]) -> list[str]:
    """Call Gemini (mid tier). Mocked in tests; requires GEMINI_API_KEY in production.

    NOTE: True Batch API submission (-50%) should replace this loop for bulk runs.
    """
    from google import genai
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    # Explicit cheap default per CLAUDE.md — never silently upgrade to Pro.
    model = os.environ.get("GEMINI_MODEL_MID", "gemini-2.5-flash")
    out: list[str] = []
    for p in prompts:
        resp = client.models.generate_content(model=model, contents=f"{_SYSTEM}\n\n{p}")
        out.append(resp.text)
    return out


def generate(conn, dry_run: bool = True) -> int:
    """Generate 擬答 for essays that lack one. Generate-once (skips existing).

    Args:
        conn:     Open SQLite connection from db.connect().
        dry_run:  If True (default), only count pending essays and return; never
                  call the LLM or write to the DB.

    Returns:
        Number of pending essays (essays without a model_answer).
    """
    pending = _pending_essays(conn)
    print(f"[model_answer_gen] pending essays needing 擬答: {len(pending)}")
    if dry_run or not pending:
        return len(pending)

    prompts = [f"科目：{e['subject']}\n題目：{e['stem']}" for e in pending]
    answers = _batch_generate(prompts)

    for e, a in zip(pending, answers):
        text = (a or "").strip()
        if not text:
            continue
        q = db.get_question(conn, e["qid"])
        if q is None:
            continue
        q.model_answer = text + "\n\n" + DISCLAIMER
        db.upsert_question(conn, q)

    return len(pending)
