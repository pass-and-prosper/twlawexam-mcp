# twexam_mcp/server.py
"""FastMCP entry point. Only wiring — no SQL, no LLM calls here."""
import os
from mcp.server.fastmcp import FastMCP

from twexam_mcp.cache import db
from twexam_mcp.tools import (
    question_search, exam_catalog, answers, statute_xref, practice, exam_map, review,
)

# Server instructions bake the study experience into the MCP so ANY client
# (desktop or the Claude mobile app via a remote connector) runs it the same way.
_INSTRUCTIONS = """台灣司律考試題庫＋學習引擎。帶使用者練題時，務必遵守：

1. 重點先行：開始練某考點前，先用 get_topic_primer 取該考點重點提示，讓使用者讀過再做題。
2. 題目一字不漏：用 get_question / practice_weak 取得題目後，題幹與選項照原文完整呈現，禁止濃縮改寫。題目本身不得上色或加粗（會洩漏答案）。
3. 作答即記錄：每題用 record_answer 記錄，驅動間隔重複與弱點地圖。
4. 詳解要講要件：解釋時從定義→要件→效果→選項逐一分析，專有名詞要解釋；用粗體與行內 code 標重點，不要用彩色圓點 emoji。
5. 弱點優先：用 practice_weak 出題（自動優先到期複習＋最弱考點）；用 get_weak_topics / get_readiness 給使用者進度與就緒度。
6. 批改完同一則訊息直接出下一輪，不要停下來問「要繼續嗎」。
"""

mcp = FastMCP("twexam", instructions=_INSTRUCTIONS)
_CONN = None


def get_conn():
    """Lazily open the question DB; fall back to in-memory seed if no DB file exists yet."""
    global _CONN
    if _CONN is not None:
        return _CONN
    path = db.default_db_path()
    if path.exists():
        _CONN = db.connect(path)
    else:
        _CONN = db.connect(":memory:")
        db.init_schema(_CONN)
        db.load_seed(_CONN)
    return _CONN


@mcp.tool()
def search_questions(query: str, limit: int = 20) -> list[dict]:
    """全文搜尋歷屆考題（匹配題幹/選項/擬答）。"""
    return question_search.search_questions(get_conn(), query, limit)


@mcp.tool()
def get_question(qid: str) -> dict:
    """以 qid（年-考試-科目-題號）取得單題結構化內容。"""
    return question_search.get_question(get_conn(), qid)


@mcp.tool()
def list_exams() -> list[dict]:
    """列出可查的考試別與年度範圍。"""
    return exam_catalog.list_exams(get_conn())


@mcp.tool()
def list_subjects(exam_code: str | None = None) -> list[str]:
    """列出科目（可選 exam_code 篩選）。"""
    return exam_catalog.list_subjects(get_conn(), exam_code)


@mcp.tool()
def get_exam_paper(year: int, exam_code: str, subject: str) -> list[dict]:
    """取整份試卷（某年·某考試·某科目全部題目）。"""
    return exam_catalog.get_exam_paper(get_conn(), year, exam_code, subject)


@mcp.tool()
def get_answer_key(year: int, exam_code: str, subject: str) -> dict:
    """取某份試卷的測驗題標準答案（題號→答案）。"""
    return answers.get_answer_key(get_conn(), year, exam_code, subject)


@mcp.tool()
def get_model_answer(qid: str) -> dict:
    """取申論題 AI 擬答（含免責聲明）。"""
    return answers.get_model_answer(get_conn(), qid)


@mcp.tool()
def search_by_statute(statute: str) -> list[dict]:
    """按法條反查考過哪些題。"""
    return statute_xref.search_by_statute(get_conn(), statute)


@mcp.tool()
def get_statute_frequency(exam_code: str | None = None) -> dict:
    """法條考頻統計（可選 exam_code）。"""
    return statute_xref.get_statute_frequency(get_conn(), exam_code)


@mcp.tool()
def random_practice(exam_code: str | None = None, subject: str | None = None,
                    q_type: str | None = None, n: int = 5,
                    seed: int | None = None, hide_answer: bool = False) -> list[dict]:
    """依條件抽題練習（hide_answer 可隱藏答案/擬答）。"""
    return practice.random_practice(get_conn(), exam_code, subject, q_type, n, seed, hide_answer)


@mcp.tool()
def get_exam_map(trial: str | None = None) -> dict:
    """考點地圖：各科目層級與核心考點（trial='sl1'/'sl2'/None=全部）。"""
    return exam_map.get_exam_map(get_conn(), trial)


@mcp.tool()
def get_topic_distribution(q_type: str | None = None, exam_code: str | None = None) -> list[dict]:
    """考點熱度排行：各 (子科目, 考點) 考過幾題（q_type='mcq'/'essay'，exam_code='sl1'/'sl2'）。"""
    return exam_map.get_topic_distribution(get_conn(), q_type, exam_code)


@mcp.tool()
def practice_by_topic(topic_point: str, topic_subject: str | None = None,
                      q_type: str | None = None, n: int = 5,
                      seed: int | None = None, hide_answer: bool = False) -> list[dict]:
    """依考點抽題練習（topic_point 為必填，如「抵押權（普通/最高限額）」）。"""
    return practice.practice_by_topic(get_conn(), topic_point, topic_subject,
                                      q_type, n, seed, hide_answer)


@mcp.tool()
def essay_exam_by_topic(topic_point: str | None = None, topic_subject: str | None = None,
                        show_answer: bool = True) -> dict:
    """考點申論題卷（模擬考）：把某考點或某子科目的所有申論題一次考出來，預設直接附 AI 擬答。
    topic_point 或 topic_subject 至少給一個；show_answer=False 可先自己作答再看擬答。"""
    return practice.essay_exam_by_topic(get_conn(), topic_point, topic_subject, show_answer)


@mcp.tool()
def record_answer(qid: str, answer: str | None = None,
                  self_correct: bool | None = None) -> dict:
    """記錄一次作答並自動批改＋更新間隔重複排程。MCQ 自動對答案；申論可傳 self_correct 自評。"""
    return review.record_answer(get_conn(), qid, answer, self_correct)


@mcp.tool()
def get_weak_topics(q_type: str = "mcq", min_attempts: int = 1, limit: int = 20) -> list[dict]:
    """弱點地圖：依個人作答正確率，由弱到強列出各考點（含答對率）。"""
    return review.get_weak_topics(get_conn(), q_type, min_attempts, limit)


@mcp.tool()
def practice_weak(n: int = 5, subject: str | None = None, q_type: str = "mcq",
                  hide_answer: bool = True) -> list[dict]:
    """弱點練習：優先出「今天到期複習」與「最弱考點」的題目（hide_answer 預設隱藏答案）。"""
    return review.practice_weak(get_conn(), n, subject, q_type, hide_answer)


@mcp.tool()
def get_progress(q_type: str = "mcq") -> dict:
    """學習總覽：總作答數、答對率、已練題數、今天到期複習數。"""
    return review.get_progress(get_conn(), q_type)


@mcp.tool()
def reset_progress() -> dict:
    """清空所有作答記錄與複習排程（重新開始）。"""
    return review.reset_progress(get_conn())


@mcp.tool()
def get_readiness(target: float = 0.60, q_type: str = "mcq", daily: int = 25) -> dict:
    """考試就緒度：依考點頻率加權推估分數、覆蓋率、最拖分考點、每日覆蓋進度（target=及格參考線）。"""
    return review.get_readiness(get_conn(), target=target, q_type=q_type, daily=daily)


@mcp.tool()
def get_topic_primer(topic_point: str) -> dict:
    """考點重點提示：做題前必讀的核心法條／常考判決釋字／學說對立／易錯陷阱。"""
    return review.get_topic_primer(get_conn(), topic_point)


def main() -> None:
    # TWEXAM_TRANSPORT=http → remote server for phone use (via a tunnel / deploy
    # + Claude.ai custom connector). Default stdio = local desktop client.
    transport = os.environ.get("TWEXAM_TRANSPORT", "stdio")
    if transport in ("http", "streamable-http"):
        from twexam_mcp.http_app import serve  # auth-gated HTTP for phone use
        serve()
    else:
        mcp.run()


if __name__ == "__main__":
    main()
