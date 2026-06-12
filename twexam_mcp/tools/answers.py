# twexam_mcp/tools/answers.py
from twexam_mcp.cache import db

DISCLAIMER = "AI 擬答為機器生成，非官方解答，不得作為應試或法律意見依據，請向權威來源驗證。"


def get_answer_key(conn, year: int, exam_code: str, subject: str) -> dict:
    paper = db.get_exam_paper(conn, year, exam_code, subject)
    return {str(q.q_no): q.answer for q in paper if q.q_type == "mcq" and q.answer}


def get_model_answer(conn, qid: str) -> dict:
    q = db.get_question(conn, qid)
    if q is None:
        return {"error": "not_found", "qid": qid}
    if q.q_type != "essay":
        return {"error": "not_an_essay", "qid": qid}
    return {"qid": qid, "model_answer": q.model_answer, "disclaimer": DISCLAIMER}
