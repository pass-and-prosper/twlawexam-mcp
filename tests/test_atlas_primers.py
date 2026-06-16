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


def test_md_table():
    md = "| 情形 | 效果 |\n|---|---|\n| 契約 | 效力未定 |\n| 單獨行為 | 無效 |"
    html = _md_to_html(md)
    assert "<table>" in html
    assert "<th>情形</th>" in html and "<th>效果</th>" in html
    assert "<td>契約</td>" in html and "<td>效力未定</td>" in html


def test_md_table_inline_markup_in_cells():
    md = "| 條 | 效果 |\n| --- | --- |\n| `§83` | **有效** |"
    html = _md_to_html(md)
    assert "<code>§83</code>" in html and "<strong>有效</strong>" in html


def test_md_hr_not_swallowed_as_table():
    # 純 --- 仍是分隔線，不可被誤判成表格分隔列
    assert "<hr>" in _md_to_html("前\n\n---\n\n後") and "<table>" not in _md_to_html("前\n\n---\n\n後")


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
            "focus": {qid: ["基線外18浬處"]},
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


def test_assemble_attaches_focus_to_question(tmp_path, monkeypatch):
    c, dbp, qid = _seed_pursuit(tmp_path)
    monkeypatch.setattr(db, "default_db_path", lambda: dbp)
    data = assemble(c)
    pid = "e:緊追權之行使要件（UNCLOS第111條）"
    q = data["detail"][pid]["114"][0]
    assert q["focus"] == ["基線外18浬處"]   # 紅虛線要框的關鍵句
    c.close()


def test_assemble_mcq_includes_options_and_correct(tmp_path, monkeypatch):
    # 一試選擇題抽屜要能顯示選項＋正解 → sl1 detail 須帶 options(list) + correct(letter)
    dbp = tmp_path / "questions.db"
    c = db.connect(dbp)
    db.init_schema(c)
    db.upsert_question(c, Question(
        113, "sl1", "民法與民事訴訟法", 9, "mcq", "下列關於法律行為之敘述，何者正確？",
        ["意思表示須一致", "要物契約即成立", "停止條件成就前已生效", "死因贈與為單獨行為"],
        answer="A", topic_subject="民法", topic_point="法律行為"))
    c.commit()
    monkeypatch.setattr(db, "default_db_path", lambda: dbp)
    data = assemble(c)
    q = data["detail"]["m:法律行為"]["113"][0]
    assert q["essay"] is False
    assert q["options"][0] == "意思表示須一致" and len(q["options"]) == 4
    assert q["correct"] == "A"
    c.close()


def test_assemble_attaches_mcq_primer(tmp_path, monkeypatch):
    # 一試考點重點(選擇題的「為什麼」)：mcq_primers.json[topic] → primers['m:'+topic]
    dbp = tmp_path / "questions.db"
    c = db.connect(dbp)
    db.init_schema(c)
    db.upsert_question(c, Question(
        113, "sl1", "民法與民事訴訟法", 9, "mcq", "關於法律行為，何者正確？",
        ["甲", "乙", "丙", "丁"], answer="A", topic_subject="民法", topic_point="法律行為"))
    c.commit()
    (tmp_path / "mcq_primers.json").write_text(
        json.dumps({"法律行為": "## 法律行為\n1. **意思表示**須健全。"}, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(db, "default_db_path", lambda: dbp)
    data = assemble(c)
    assert "<strong>意思表示</strong>" in data["primers"]["m:法律行為"]
    c.close()


def test_assemble_attaches_mcq_explanation(tmp_path, monkeypatch):
    # 選擇題逐項詳解：mcq_explanations.json[qid] → detail 該題 entry["explanation"]（渲染後 HTML）
    dbp = tmp_path / "questions.db"
    c = db.connect(dbp)
    db.init_schema(c)
    db.upsert_question(c, Question(
        113, "sl1", "民法與民事訴訟法", 9, "mcq", "關於法律行為，何者正確？",
        ["甲", "乙", "丙", "丁"], answer="D", topic_subject="民法", topic_point="法律行為"))
    qid = "113-sl1-民法與民事訴訟法-9"
    c.commit()
    (tmp_path / "mcq_explanations.json").write_text(
        json.dumps({qid: "## 為什麼 D\n依 `§83` 詐術→**有效**。"}, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(db, "default_db_path", lambda: dbp)
    data = assemble(c)
    q = data["detail"]["m:法律行為"]["113"][0]
    assert "<code>§83</code>" in q["explanation"] and "<strong>有效</strong>" in q["explanation"]
    c.close()


def test_assemble_no_explanation_when_absent(tmp_path, monkeypatch):
    # 沒有 mcq_explanations.json（或該題未收）時不可炸，entry 無 explanation 鍵
    dbp = tmp_path / "questions.db"
    c = db.connect(dbp)
    db.init_schema(c)
    db.upsert_question(c, Question(
        113, "sl1", "民法與民事訴訟法", 9, "mcq", "關於法律行為，何者正確？",
        ["甲", "乙", "丙", "丁"], answer="D", topic_subject="民法", topic_point="法律行為"))
    c.commit()
    monkeypatch.setattr(db, "default_db_path", lambda: dbp)
    data = assemble(c)
    assert "explanation" not in data["detail"]["m:法律行為"]["113"][0]
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
