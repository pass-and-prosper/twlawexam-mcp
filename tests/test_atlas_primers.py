# tests/test_atlas_primers.py
"""考點重點(primer) + 各題擬答(answer) 注入 render_atlas 的地圖。

- _md_to_html: 把手寫 markdown(粗體/行內code/標題/編號清單/巢狀/分隔線)轉安全 HTML。
- assemble(): 依 canonical 爭點名把 primer 掛到爭點(id='e:'+canon)、把 answers 掛到對應 qid。
"""
import json

from twexam_mcp.cache import db
from twexam_mcp.models.question import Question
from scripts.render_atlas import _md_to_html, assemble


# ---------- _md_to_html (pure) ----------

def test_md_bold():
    assert "<strong>起追地點</strong>" in _md_to_html("**起追地點**")


def test_md_inline_code():
    assert "<code>§111</code>" in _md_to_html("行使依據 `§111`")


def test_md_heading():
    assert "<h4>緊追權之行使要件</h4>" in _md_to_html("## 緊追權之行使要件")


def test_md_ordered_list():
    html = _md_to_html("1. 起追地點\n2. 起追時機")
    assert "<ol>" in html and "<li>起追地點</li>" in html and "<li>起追時機</li>" in html


def test_md_nested_bullets_under_ordered_item():
    # 數字項下的縮排 bullet 要變成「巢狀在該 <li> 內」的 <ul>
    html = _md_to_html("1. 起追地點\n   - 在鄰接區起追\n2. 起追時機")
    assert "<li>起追地點<ul><li>在鄰接區起追</li></ul></li>" in html


def test_md_hr():
    assert "<hr>" in _md_to_html("---")


def test_md_escapes_html():
    # 安全紅線：使用者內容裡的尖角括號必須 escape，不可變成裸標籤
    out = _md_to_html("看 <script>alert(1)</script> 注意")
    assert "<script>" not in out and "&lt;script&gt;" in out


# ---------- assemble() wiring ----------

def _seed_pursuit(tmp_path):
    """建一個臨時 DB：一題海洋法申論，essay_issue 經 issue_canon 對到緊追權 canonical。"""
    dbp = tmp_path / "questions.db"
    c = db.connect(dbp)
    db.init_schema(c)
    db.upsert_question(c, Question(
        114, "sl2", "海商法與海洋法", 3, "essay",
        "A 國海巡船艦在基線外18浬處發現B 國漁船載運偷渡客……",
        topic_subject="海商法與海洋法", topic_point="緊追權", model_answer="..."))
    qid = "114-sl2-海商法與海洋法-3"
    c.execute("INSERT INTO essay_issues(qid, issue_no, issue, doctrines, practice, topic_subject) "
              "VALUES(?,?,?,?,?,?)", (qid, 1, "緊追權能否作為管轄例外", "[]", "[]", "海商法與海洋法"))
    c.execute("INSERT INTO issue_canon(issue, canonical, topic_subject) VALUES(?,?,?)",
              ("緊追權能否作為管轄例外", "緊追權之行使要件（UNCLOS第111條）", "海商法與海洋法"))
    c.commit()
    (tmp_path / "issue_primers.json").write_text(json.dumps({
        "緊追權之行使要件（UNCLOS第111條）": {
            "primer": "## 要件\n1. **起追地點**：須在內水／領海內。",
            "answers": {qid: "**114-3（鄰接區18浬）** 核心：`§33` 移民管制可緊追。"},
        }
    }, ensure_ascii=False), encoding="utf-8")
    return c, dbp, qid


def test_assemble_attaches_primer_to_canonical_issue(tmp_path, monkeypatch):
    c, dbp, qid = _seed_pursuit(tmp_path)
    monkeypatch.setattr(db, "default_db_path", lambda: dbp)
    data = assemble(c)
    pid = "e:緊追權之行使要件（UNCLOS第111條）"
    assert pid in data["primers"]
    assert "<strong>起追地點</strong>" in data["primers"][pid]
    c.close()


def test_assemble_attaches_answer_to_question(tmp_path, monkeypatch):
    c, dbp, qid = _seed_pursuit(tmp_path)
    monkeypatch.setattr(db, "default_db_path", lambda: dbp)
    data = assemble(c)
    pid = "e:緊追權之行使要件（UNCLOS第111條）"
    q = data["detail"][pid]["114"][0]
    assert q["qid"] == qid
    assert "<code>§33</code>" in q["answer"]
    c.close()


def test_assemble_no_primer_when_absent(tmp_path, monkeypatch):
    # 沒有 issue_primers.json 時不可炸，primers 為空 dict、題目無 answer
    c, dbp, qid = _seed_pursuit(tmp_path)
    (tmp_path / "issue_primers.json").unlink()
    monkeypatch.setattr(db, "default_db_path", lambda: dbp)
    data = assemble(c)
    assert data["primers"] == {}
    assert "answer" not in data["detail"]["e:緊追權之行使要件（UNCLOS第111條）"]["114"][0]
    c.close()
