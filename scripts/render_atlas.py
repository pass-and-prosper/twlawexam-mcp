#!/usr/bin/env python
"""Unified interactive 考點地圖 (選擇 + 申論 合併) → self-contained HTML.

By 科目, horizontally switchable. Each 考點 / 爭點 shows a row of YEAR CIRCLES —
one circle per 民國 year it was tested, the year inside, ×N if several that year.
Circle colour: 藍 = that year was 選擇(MCQ) only, 橘 = that year had a 申論(essay);
recent years are darker. Click a year-circle → a drawer lists that year's original
questions (stem, and 學說/實務 for essays). 未考過 是用內容關鍵字判斷（不信分類標籤）.

Usage:  python scripts/render_atlas.py [out.html]   # default topic-atlas.html
"""
from __future__ import annotations
import html
import json
import re
import sys
from pathlib import Path

from twexam_mcp.cache import db
from twexam_mcp.tools.exam_map import _SL1_MAP, _SL2_MAP, _all_syllabus_topics


# ── 手寫 markdown → 安全 HTML（考點重點 / 擬答用；不依賴外部套件）─────────────
_MD_BOLD = re.compile(r"\*\*(.+?)\*\*")
_MD_CODE = re.compile(r"`([^`]+)`")
_MD_LIST = re.compile(r"^(\s*)([-*]|\d+\.)\s+(.*)$")


def _md_inline(text: str) -> str:
    # 先 escape（安全紅線：使用者內容裡的尖角括號不可變裸標籤），再上行內標記
    t = html.escape(text, quote=False)
    t = _MD_CODE.sub(lambda m: f"<code>{m.group(1)}</code>", t)
    t = _MD_BOLD.sub(lambda m: f"<strong>{m.group(1)}</strong>", t)
    return t


def _md_list(items: list[tuple[int, bool, str]], idx: int, base: int) -> tuple[str, int]:
    """items=(indent, ordered, text)；依縮排把較深的項目巢狀進上一個 <li>。"""
    tag = "ol" if items[idx][1] else "ul"
    parts = [f"<{tag}>"]
    while idx < len(items):
        indent, _ordered, text = items[idx]
        if indent < base:
            break
        li = f"<li>{_md_inline(text)}"
        idx += 1
        if idx < len(items) and items[idx][0] > base:
            sub, idx = _md_list(items, idx, items[idx][0])
            li += sub
        parts.append(li + "</li>")
    parts.append(f"</{tag}>")
    return "".join(parts), idx


def _md_to_html(md: str) -> str:
    """支援的子集：## 標題、**粗體**、`行內碼`、編號/項目清單(含一層巢狀)、--- 分隔線、段落。"""
    lines = (md or "").strip("\n").split("\n")
    out: list[str] = []
    para: list[str] = []

    def flush():
        if para:
            out.append("<p>" + "<br>".join(_md_inline(x) for x in para) + "</p>")
            para.clear()

    i = 0
    while i < len(lines):
        line = lines[i]
        if not line.strip():
            flush(); i += 1; continue
        if re.match(r"^#{2,6}\s+", line):
            flush(); out.append(f"<h4>{_md_inline(line.lstrip('#').strip())}</h4>"); i += 1; continue
        if re.match(r"^-{3,}\s*$", line):
            flush(); out.append("<hr>"); i += 1; continue
        if _MD_LIST.match(line):
            flush()
            items: list[tuple[int, bool, str]] = []
            while i < len(lines) and _MD_LIST.match(lines[i]):
                m = _MD_LIST.match(lines[i])
                items.append((len(m.group(1)), m.group(2).endswith("."), m.group(3)))
                i += 1
            out.append(_md_list(items, 0, items[0][0])[0])
            continue
        para.append(line.strip())
        i += 1
    flush()
    return "\n".join(out)


def assemble(conn) -> dict:
    # questions by topic_point & year, split by 選擇/申論
    mcq: dict[str, dict] = {}   # topic -> {year:[q]}
    es_t: dict[str, dict] = {}  # topic -> {year:[q]}  (essays, by topic_point)
    for qid, year, stem, tp, qtype, options, answer in conn.execute(
        "SELECT qid, year, stem, topic_point, q_type, options, answer FROM questions WHERE topic_point IS NOT NULL"
    ):
        bucket = es_t if qtype == "essay" else mcq
        entry = {"qid": qid, "year": year, "stem": stem, "essay": qtype == "essay"}
        if qtype != "essay" and options:  # 選擇題：帶選項＋正解(letter，避開申論的 q.answer 擬答)
            entry["options"] = json.loads(options)
            entry["correct"] = answer
        bucket.setdefault(tp, {}).setdefault(year, []).append(entry)

    # doctrines/practice per essay qid (aggregate that essay's 爭點)
    dp: dict[str, dict] = {}
    for qid, doc, prac in conn.execute("SELECT qid, doctrines, practice FROM essay_issues"):
        d = dp.setdefault(qid, {"doctrines": [], "practice": []})
        d["doctrines"] += json.loads(doc)
        d["practice"] += json.loads(prac)
    for yrs in es_t.values():
        for qs in yrs.values():
            for q in qs:
                q.update(dp.get(q["qid"], {}))

    # canonical 爭點 (申論 lens) for sl2
    ess_canon: dict[str, dict] = {}
    canon_subject: dict[str, str] = {}
    for qid, year, stem, issue, canon, doc, prac, ts in conn.execute(
        """SELECT e.qid, q.year, q.stem, e.issue, COALESCE(c.canonical, e.issue),
                  e.doctrines, e.practice, e.topic_subject
           FROM essay_issues e JOIN questions q ON q.qid=e.qid
           LEFT JOIN issue_canon c ON c.issue=e.issue"""
    ):
        # dedup by qid within (canon, year): one essay with 2 issues mapping to the
        # same canonical 爭點 must count ONCE (merge its 學說/實務), not show ×2.
        slot = ess_canon.setdefault(canon, {}).setdefault(year, {})
        if qid in slot:
            slot[qid]["doctrines"] += json.loads(doc)
            slot[qid]["practice"] += json.loads(prac)
        else:
            slot[qid] = {"qid": qid, "year": year, "stem": stem, "essay": True,
                         "doctrines": json.loads(doc), "practice": json.loads(prac), "issue": issue}
        canon_subject[canon] = ts

    detail: dict[str, dict] = {}

    def entry_topic(idd, label, mcq_y, ess_y):
        det, years = {}, []
        for y in sorted(set(mcq_y) | set(ess_y)):
            m, e = mcq_y.get(y, []), ess_y.get(y, [])
            years.append({"year": y, "count": len(m) + len(e), "essay": len(e) > 0})
            det[str(y)] = m + e
        detail[idd] = det
        total = sum(yy["count"] for yy in years)
        return {"id": idd, "label": label, "years": years, "total": total, "examined": total > 0}

    sl1 = []
    for it in _SL1_MAP:
        groups = [{"name": ss["name"],
                   "topics": [entry_topic("m:" + t, t, mcq.get(t, {}), {})  # 一試只放選擇題
                              for t in ss["topics"]]}
                  for ss in it["sub_subjects"]]
        sl1.append({"subject": it["subject"], "groups": groups})

    def entry_canon(idd, label, by_year, answers=None, focus=None):
        answers = answers or {}
        focus = focus or {}
        rows = {str(y): list(by_year[y].values()) for y in by_year}  # by_year[y] is {qid:entry}
        for qs in rows.values():
            for q in qs:
                if q["qid"] in answers:  # 各題擬答（單年抽屜才顯示，由 JS 控制）
                    q["answer"] = _md_to_html(answers[q["qid"]])
                if q["qid"] in focus:    # 題幹要紅虛線框的關鍵句（該爭點觸發點）
                    q["focus"] = focus[q["qid"]]
        detail[idd] = rows
        years = [{"year": y, "count": len(by_year[y]), "essay": True} for y in sorted(by_year)]
        total = sum(len(v) for v in by_year.values())
        return {"id": idd, "label": label, "years": years, "total": total,
                "examined": total > 0, "recurring": total >= 2}

    by_subject: dict[str, list] = {}
    for canon, by_year in ess_canon.items():
        by_subject.setdefault(canon_subject[canon], []).append((canon, by_year))
    order = [it["subject"] for it in _SL2_MAP]
    subj_keys = sorted(by_subject, key=lambda s: (order.index(s) if s in order else 99, s))

    # 研究推測的「重要但還沒考過」爭點 (agent 查 + legal-db 驗字號) — bundled JSON
    upath = db.default_db_path().parent / "untested_issues.json"
    untested = json.loads(upath.read_text(encoding="utf-8")) if upath.exists() else {}

    # tested 爭點 enrich 後的學說(含學者)/實務(具體字號)，覆蓋擬答抽出的籠統版 — bundled JSON
    epath = db.default_db_path().parent / "issue_enrich.json"
    enrich_raw = json.loads(epath.read_text(encoding="utf-8")) if epath.exists() else {}
    enrich = {"e:" + canon: v for canon, v in enrich_raw.items()}

    # 考點重點(primer) + 各題擬答(answers) — 依 canonical 爭點名手寫 markdown，bundled JSON
    ppath = db.default_db_path().parent / "issue_primers.json"
    primers_src = json.loads(ppath.read_text(encoding="utf-8")) if ppath.exists() else {}
    primers: dict[str, str] = {}  # id('e:'+canon / 'm:'+topic) -> 渲染後的重點 HTML

    # 一試考點重點（選擇題的「為什麼」）— 依考點名手寫 markdown，id='m:'+topic
    mpath = db.default_db_path().parent / "mcq_primers.json"
    mcq_primers = json.loads(mpath.read_text(encoding="utf-8")) if mpath.exists() else {}
    for topic, md in mcq_primers.items():
        if md:
            primers["m:" + topic] = _md_to_html(md)

    sl2 = []
    n_untested = 0
    for ts in subj_keys:
        issues = []
        for canon, by_year in by_subject[ts]:
            pid = "e:" + canon
            pdata = primers_src.get(canon, {})
            issues.append(entry_canon(pid, canon, by_year, pdata.get("answers"), pdata.get("focus")))
            if pdata.get("primer"):
                primers[pid] = _md_to_html(pdata["primer"])
        issues.sort(key=lambda x: (-x["total"], x["label"]))
        uts = []
        for j, u in enumerate(untested.get(ts, [])):
            uid = f"u:{ts}:{j}"
            detail[uid] = [{"untested": True, "issue": u["issue"], "why": u.get("why", ""),
                            "doctrines": u.get("doctrines", []), "practice": u.get("practice", []),
                            "source": u.get("source", ""), "gk_source": u.get("gk_source", ""),
                            "ls_source": u.get("ls_source", ""), "journal_source": u.get("journal_source", "")}]
            uts.append({"id": uid, "label": u["issue"], "source": u.get("source", "")})
        n_untested += len(uts)
        sl2.append({"subject": ts, "issues": issues, "untested": uts})

    # 未考過：不信分類標籤(會誤標)，改用內容關鍵字(含縮寫同義詞)是否出現
    tested = {r[0] for r in conn.execute(
        "SELECT DISTINCT topic_point FROM questions WHERE topic_point IS NOT NULL")}
    syn = {
        "勞保/健保": ["勞工保險", "全民健康保險", "勞保", "健保"],
        "公司重整/清算": ["重整", "清算"],
        "操縱市場": ["操縱", "炒作", "沖洗買賣", "相對委託", "拉抬"],
        "物權變動": ["物權變動", "善意取得"],
        "認罪協商": ["認罪協商", "協商程序"],
        "海難救助": ["海難救助", "救助報酬", "施救"],
        "非訟事件": ["非訟"],
    }

    def _seen(kw):
        return conn.execute(
            "SELECT 1 FROM questions WHERE stem LIKE ? OR options LIKE ? OR model_answer LIKE ? LIMIT 1",
            (f"%{kw}%",) * 3).fetchone() is not None

    # 國文（作文）文體（議論文/說明文/法律時事評析）是寫作類型、非實體法律考點，
    # 題幹永遠不會出現該詞 → 一律排除出「未考過」偵測（依科目名抓，未來新增文體自動排除）
    essay_genres = {t for it in _SL2_MAP if ("國文" in it["subject"] or "作文" in it["subject"])
                    for t in it["topics"]}
    uncovered_list = [t for t in sorted(_all_syllabus_topics())
                      if t not in tested and t not in essay_genres
                      and not any(_seen(k) for k in syn.get(t, [t]))]

    return {
        "sl1": sl1, "sl2": sl2, "detail": detail, "uncovered_list": uncovered_list,
        "primers": primers, "enrich": enrich,
        "summary": {
            "mcq_topics": len(_all_syllabus_topics()),
            "essay_issues": sum(len(s["issues"]) for s in sl2),
            "uncovered": len(uncovered_list),
            "untested": n_untested,
            "total_q": conn.execute("SELECT COUNT(*) FROM questions").fetchone()[0],
        },
    }


_CSS = """
:root{--bg:#f5f5f7;--card:#fff;--ink:#1d1d1f;--muted:#86868b;--blue:#0071e3;--orange:#ff9500;--line:#e5e5ea;}
*{box-sizing:border-box;}
body{margin:0;background:var(--bg);color:var(--ink);letter-spacing:-.01em;
 font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Inter,"PingFang TC","Microsoft JhengHei",sans-serif;}
.topbar{position:sticky;top:0;z-index:9;padding:16px 26px;background:rgba(245,245,247,.8);
 backdrop-filter:saturate(180%) blur(20px);border-bottom:1px solid var(--line);display:flex;gap:14px;align-items:center;flex-wrap:wrap;}
.topbar h1{font-size:19px;margin:0;font-weight:600;}
.chip{font-size:13px;padding:5px 12px;border-radius:980px;background:#ececf0;color:var(--muted);font-weight:500;}
.chip b{color:var(--ink);}
.tabs{display:flex;gap:8px;margin-left:auto;}
.tab{font-size:14px;font-weight:600;padding:7px 16px;border-radius:980px;border:none;background:#e8e8ed;color:#3a3a3c;cursor:pointer;}
.tab.on{background:var(--blue);color:#fff;}
.subbar{display:flex;gap:8px;overflow-x:auto;padding:11px 22px;background:#eef0f3;border-bottom:1px solid var(--line);
 -webkit-overflow-scrolling:touch;scrollbar-width:thin;}
.sbtn{flex:0 0 auto;font-size:13px;font-weight:500;padding:6px 14px;border-radius:980px;border:1px solid var(--line);
 background:#fff;color:#3a3a3c;cursor:pointer;white-space:nowrap;}
.sbtn:hover{border-color:#c7c7cc;}
.sbtn.on{background:var(--blue);color:#fff;border-color:var(--blue);}
.sbtn.uc.on{background:var(--orange);border-color:var(--orange);}
.legend{max-width:1080px;margin:14px auto 0;padding:0 22px;font-size:12.5px;color:var(--muted);display:flex;gap:16px;flex-wrap:wrap;}
.legend .d{display:inline-block;width:13px;height:13px;border-radius:50%;vertical-align:-2px;margin-right:5px;}
.wrap{max-width:1080px;margin:0 auto;padding:14px 20px 90px;}
.card{background:var(--card);border:1px solid var(--line);border-radius:18px;padding:16px 20px;margin-bottom:14px;box-shadow:0 1px 3px rgba(0,0,0,.04);}
.card h3{margin:0 0 3px;font-size:17.5px;font-weight:600;}
.card .meta{font-size:13px;color:var(--muted);margin-bottom:12px;}
.gname{font-size:13.5px;font-weight:600;color:#6e6e73;margin:16px 0 8px;}
.row{display:flex;align-items:center;gap:14px;padding:9px 0;border-bottom:1px solid #f3f3f6;}
.label{flex:0 0 280px;font-size:15px;cursor:pointer;line-height:1.5;}
.row:hover .label{color:var(--blue);}
.row.recur .label{font-weight:600;}
.circs{display:flex;flex-wrap:wrap;gap:7px;align-items:center;}
.circ{position:relative;width:40px;height:40px;border-radius:50%;display:flex;align-items:center;justify-content:center;
 font-size:13px;font-weight:700;cursor:pointer;transition:transform .08s;box-shadow:0 1px 2px rgba(0,0,0,.12);}
.circ:hover{transform:scale(1.08);}
.circ i{position:absolute;top:-4px;right:-6px;font-style:normal;font-size:10px;font-weight:700;color:#fff;
 background:#5a5a5e;border-radius:980px;padding:0 5px;line-height:15px;}
.circ.none{width:auto;height:auto;border-radius:980px;padding:5px 12px;background:#fff;border:1.5px dashed var(--orange);
 color:#9a5b00;font-size:12px;cursor:default;box-shadow:none;}
.hidden{display:none;}
.scrim{position:fixed;inset:0;background:rgba(0,0,0,.25);opacity:0;pointer-events:none;transition:.2s;z-index:20;}
.scrim.on{opacity:1;pointer-events:auto;}
.drawer{position:fixed;top:0;right:0;height:100%;width:100vw;background:var(--card);z-index:21;
 transform:translateX(100%);transition:transform .24s cubic-bezier(.4,0,.2,1);box-shadow:-8px 0 40px rgba(0,0,0,.18);display:flex;flex-direction:column;}
.drawer.on{transform:translateX(0);}
.drawer header{padding:20px 28px;border-bottom:1px solid var(--line);display:flex;gap:12px;align-items:flex-start;}
.drawer header h2{font-size:18px;margin:0;font-weight:600;line-height:1.45;flex:1;}
.drawer .x{border:none;background:#e8e8ed;border-radius:50%;width:32px;height:32px;font-size:17px;cursor:pointer;color:#3a3a3c;flex:0 0 auto;}
.drawer .body{overflow:auto;padding:14px 30px 46px;}
/* 全螢幕配版：題目｜解析 兩欄；窄螢幕收成單欄 */
.cols{display:grid;grid-template-columns:minmax(0,1.6fr) minmax(0,1fr);gap:30px;align-items:start;max-width:1700px;margin:0 auto;}
.col-q,.col-a{min-width:0;}
.col-q{position:sticky;top:0;align-self:start;}
.solo{max-width:1040px;margin:0 auto;}
@media(max-width:1080px){.cols{grid-template-columns:1fr;gap:0;}.col-q{position:static;}}
.q{padding:18px 0;border-bottom:1px solid var(--line);}
.q .yr{display:inline-block;font-size:13px;font-weight:700;color:#fff;background:var(--blue);padding:3px 11px;border-radius:980px;margin-right:9px;}
.q .qid{font-size:12.5px;color:var(--muted);}
/* 左欄題目（閱讀心理學排版）：收窄行寬→眼睛好回掃、加大行高→密集中文不擠、
   事實段回流、試問分塊編號；題幹一律不上色不加粗（避免洩答） */
.q .stem{margin:14px 0 0;font-size:17px;line-height:2.02;color:var(--ink);
 letter-spacing:.005em;max-width:38em;white-space:normal;text-wrap:pretty;}
.q .stem .st-narr{margin:0;}
.q .stem .st-narr+.st-narr{margin-top:11px;}
.q .stem .st-ask{margin-top:22px;}
.q .stem .st-ask-lead{display:inline-block;font-size:12.5px;font-weight:700;color:#6e6e73;
 letter-spacing:.16em;background:#f0f0f3;border-radius:980px;padding:3px 13px 3px 15px;margin-bottom:13px;}
.q .stem .st-qs{list-style:none;counter-reset:sq;padding:0;margin:0;display:flex;flex-direction:column;gap:12px;}
.q .stem .st-qs>li{counter-increment:sq;position:relative;padding:13px 17px 13px 46px;
 background:#fbfbfd;border:1px solid #ececf0;border-radius:14px;line-height:1.95;}
.q .stem .st-qs>li::before{content:counter(sq);position:absolute;left:13px;top:12px;
 width:25px;height:25px;background:#e8e8ed;color:#48484a;border-radius:50%;letter-spacing:0;
 font-size:13px;font-weight:700;display:flex;align-items:center;justify-content:center;}
.q .stem .st-q-single{margin-top:2px;padding:13px 17px;background:#fbfbfd;
 border:1px solid #ececf0;border-radius:14px;line-height:1.95;}
.q .tag{font-size:12.5px;font-weight:800;color:#6e6e73;margin-top:14px;letter-spacing:.02em;}
.q .tag.doc-t{color:#0a6cff;}      /* 學說＝藍 */
.q .tag.prac-t{color:#1b9e57;}     /* 實務＝綠 */
.q .di{font-size:14.5px;line-height:1.85;background:#eef4ff;border-left:3px solid #0a6cff;border-radius:0 10px 10px 0;padding:10px 14px;margin:6px 0;}
.q .pr{font-size:14px;line-height:1.8;background:#e9f8f0;border-left:3px solid #1b9e57;border-radius:0 10px 10px 0;padding:10px 14px;margin:6px 0;color:#0c6b3c;}
/* 選擇題選項：正解綠底打勾 */
.opts{margin-top:11px;display:flex;flex-direction:column;gap:7px;}
.opthint{font-size:12px;color:#86868b;margin:0 0 3px 2px;}
.opts.answered .opthint{display:none;}
.opt{font-size:14px;line-height:1.7;background:#f5f5f7;border:1px solid transparent;border-radius:10px;padding:9px 13px;display:flex;gap:9px;align-items:baseline;cursor:pointer;transition:background .1s;}
.opts:not(.answered) .opt:hover{background:#e6eefb;}
.opts.answered .opt{cursor:default;}
.opt .ol{font-weight:800;color:#86868b;flex:0 0 auto;}
.opt .ot{flex:1;}
.opt.ok{background:#e9f8f0;border-color:#a5dcb9;}
.opt.ok .ol{color:#1b9e57;}
.opt.wrong{background:#ffeceb;border-color:#ffc4bf;}
.opt.wrong .ol{color:#ff3b30;}
.opt .ck{margin-left:auto;color:#1b9e57;font-weight:800;font-size:12px;flex:0 0 auto;white-space:nowrap;}
.opt .ck.wrongck{color:#ff3b30;}
.di .enum{color:#0a6cff;font-weight:800;}    /* 學說標號＝藍 */
.pr .enum{color:#1b9e57;font-weight:800;}    /* 實務標號＝綠 */
/* 題幹裡該爭點的關鍵句：紅虛線框（提醒「這裡是考點」），題幹其餘維持純黑 */
.q .stem .focus{border:1.6px dashed #ff3b30;border-radius:7px;padding:1px 5px;margin:0 1px;
 background:rgba(255,59,48,.06);box-decoration-break:clone;-webkit-box-decoration-break:clone;}
.ucard{border:1px solid #ffe0b8;background:#fffaf3;}
.pills{display:flex;flex-wrap:wrap;gap:7px;}
.upill{font-size:13px;padding:5px 11px;border-radius:980px;background:#fff;border:1.5px dashed var(--orange);color:#9a5b00;font-weight:500;}
.gname.pred{color:#6a3df0;margin-top:20px;}
.circ.pred{width:auto;height:auto;border-radius:980px;padding:5px 12px;background:#f3eeff;border:1.5px solid #cdbcff;
 color:#6a3df0;font-size:12px;box-shadow:none;}
.circ.pred.gk{background:#e6f6ec;border-color:#a5dcb9;color:#0a7d3c;}
.circ.pred.jr{background:#fcefe2;border-color:#f0c79e;color:#b8500a;}
.circ.pred.ls{background:#f0eafc;border-color:#cbb6ee;color:#7a4ad0;}
.row.ut .label{color:#4a3a8c;}
.row.ut:hover .label{color:#6a3df0;}
/* 擬答＝橘（行動·你要寫的） */
.q .tag.ans-t{color:#e07b00;}
.ans{font-size:15px;line-height:1.9;background:#fff6ea;border:1px solid #ffe2bd;border-left:3px solid #ff9500;
 border-radius:0 10px 10px 0;padding:12px 16px;margin-top:6px;}
/* 考點重點＝紫（要件 chunk 化、數字徽章好背） */
.primer{margin-top:26px;background:#faf8ff;border:1px solid #e7defc;border-radius:16px;padding:18px 22px;box-shadow:0 1px 3px rgba(106,61,240,.06);}
.primer .ptag{font-size:14px;font-weight:800;color:#6a3df0;letter-spacing:.06em;margin-bottom:12px;text-align:center;}
.md{font-size:14.5px;line-height:1.9;color:var(--ink);}
.md h4{font-size:15.5px;font-weight:700;margin:16px 0 8px;color:#4a2db5;}
.md h4:first-child{margin-top:0;}
.md p{margin:9px 0;}
.md ol,.md ul{margin:8px 0;padding-left:24px;}
.md li{margin:7px 0;line-height:1.85;}
.md ul{list-style:disc;}
/* 要件用紫色數字徽章：chunk 化，一眼數出「幾個要件」 */
.primer .md ol{counter-reset:rq;list-style:none;padding-left:0;}
.primer .md ol>li{counter-increment:rq;position:relative;padding-left:34px;margin:11px 0;}
.primer .md ol>li::before{content:counter(rq);position:absolute;left:0;top:1px;width:23px;height:23px;
 background:#6a3df0;color:#fff;border-radius:50%;font-size:12.5px;font-weight:800;
 display:flex;align-items:center;justify-content:center;box-shadow:0 1px 3px rgba(106,61,240,.35);}
.primer .md ul{padding-left:20px;}
.md code{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;font-size:13.5px;
 background:#ece6fb;color:#5b2bd6;padding:1px 6px;border-radius:5px;font-weight:600;}
/* 必背關鍵：粗體上黃螢光（記憶錨點） */
.md strong{font-weight:700;background:linear-gradient(transparent 58%,#ffe79e 58%);padding:0 1px;border-radius:2px;}
.md hr{border:none;border-top:1px solid #e7defc;margin:14px 0;}
"""

_JS = """
const $=s=>document.querySelector(s);
const BLUE={109:'#dcecfb',110:'#bcdcfa',111:'#94c6f6',112:'#5aa6f0',113:'#2f8be8',114:'#0a5fc2'};
function esc(s){return (s+'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));}
// (1)文→(1) 文：學說/實務內嵌標號補空白＋上色，讀起來不擠
function beautify(s){return s.replace(/([(（][0-9]+[)）])/g,'<b class="enum">$1</b> ');}
// 題幹裡「該爭點觸發的關鍵句」用紅虛線框起來（focus 為精準子字串陣列）
// 長→短排序＋佔位符：避免「短focus ⊂ 長focus」時短的先套插了 span 破壞長的比對（同題多爭點常見）
function markFocus(stem,focus){let h=esc(stem);
  const fs=[...new Set(focus||[])].filter(Boolean).sort((a,b)=>b.length-a.length);
  const slots=[];
  fs.forEach(f=>{const ef=esc(f);if(!ef)return;if(h.indexOf(ef)<0)return;
    h=h.split(ef).join('\\u0000'+slots.length+'\\u0001');slots.push(ef);});
  return h.replace(/\\u0000(\\d+)\\u0001/g,(_,i)=>'<span class="focus">'+slots[+i]+'</span>');}
// 左欄題目排版（閱讀心理學）：併掉 PDF 硬換行讓事實段回流、試問依（N分）分塊編號；
// 只動換行、不動任何字、不上色加粗（守題庫鐵律不洩答）。focus 子字串不含換行→重排後仍精準框。
function formatStem(stem,focus){
  if(!stem) return '';
  let s=(stem+'').replace(/\\r/g,'').replace(/[｜|]\\s*$/,'').trim();
  const reflow=t=>t.replace(/[ \\t]*\\n[ \\t]*/g,'').trim();   // 只併換行，保留行內單一空格(如「A 地」)→ focus 不破
  let narrative=s,label=false,qpart='';
  const m=s.match(/試\\s*問\\s*[：:]/);
  if(m){ narrative=s.slice(0,m.index); label=m[0]; qpart=s.slice(m.index+m[0].length); }
  else { const m2=s.match(/試\\s*[問說述論擬答回析陳]|問\\s*[：:]/);
    if(m2&&m2.index>0){ narrative=s.slice(0,m2.index); qpart=s.slice(m2.index); } }
  const narrHtml=narrative.split(/\\n[ \\t]*\\n/).map(reflow).filter(Boolean)
    .map(p=>`<p class="st-narr">${markFocus(p,focus)}</p>`).join('');
  if(!qpart.trim()) return narrHtml||`<p class="st-narr">${markFocus(reflow(s),focus)}</p>`;
  let items=[],last=0,r;const re=/（\\s*\\d+\\s*分\\s*）/g;
  while((r=re.exec(qpart))){ items.push(qpart.slice(last,r.index+r[0].length)); last=r.index+r[0].length; }
  const tail=qpart.slice(last).trim(); if(tail) items.push(tail);
  items=items.map(reflow).filter(Boolean);
  const lead=label?`<div class="st-ask-lead">${esc(label)}</div>`:'';
  const body=items.length>=2
    ? `<ol class="st-qs">${items.map(it=>`<li>${markFocus(it,focus)}</li>`).join('')}</ol>`
    : `<div class="st-q-single">${markFocus(items[0]||reflow(qpart),focus)}</div>`;
  return narrHtml+`<div class="st-ask">${lead}${body}</div>`;
}
// 選擇題：先作答後揭示正解（點選作答 → ✓正解／✗你選的）
function optionsHtml(options,correct){const L='ABCDEFGHIJ';
  const opts=options.map((o,i)=>`<div class="opt" data-letter="${L[i]}"><span class="ol">${L[i]}</span><span class="ot">${esc(o)}</span></div>`).join('');
  return `<div class="opts" data-correct="${esc(correct)}"><div class="opthint">👆 點選作答，再顯示正解</div>${opts}</div>`;}
function srcMeta(s){
  if(s==='高普考領先') return {b:'📈 高普考', c:'gk', bg:'#0a7d3c'};
  if(s==='法律系考古題') return {b:'🎓 法律系', c:'ls', bg:'#7a4ad0'};
  if(s==='期刊論文') return {b:'📚 期刊', c:'jr', bg:'#b8500a'};
  return {b:'🔮 推測', c:'', bg:'#7b5cff'};
}
function circles(e){
  if(!e.examined) return '<span class="circ none">未考</span>';
  return e.years.map(y=>{
    const fill=BLUE[y.year]||'#7fbef9';
    const badge=y.count>1?`<i>×${y.count}</i>`:'';
    return `<span class="circ" data-id="${esc(e.id)}" data-year="${y.year}" title="${y.year}年 ${y.count}題"
      style="background:${fill};color:${y.year>=112?'#fff':'#06294d'}">${y.year}${badge}</span>`;
  }).join('');
}
function latestYr(t){return t.years&&t.years.length?Math.max(...t.years.map(y=>y.year)):0;}
function rows(items,recur){
  const sorted=[...items].sort((a,b)=>latestYr(b)-latestYr(a)||b.total-a.total);
  return sorted.map(t=>`<div class="row${recur&&t.recurring?' recur':''}">
    <span class="label" data-id="${esc(t.id)}">${esc(t.label)}</span>
    <span class="circs">${circles(t)}</span></div>`).join('');
}
function subjectCard(tab,sub){
  if(tab==='sl1'){
    const tot=sub.groups.reduce((a,g)=>a+g.topics.reduce((b,t)=>b+t.total,0),0);
    const gs=sub.groups.map(g=>`<div class="gname">${esc(g.name)}</div>${rows(g.topics,false)}`).join('');
    return `<div class="card"><h3>${esc(sub.subject)}</h3><div class="meta">合計 ${tot} 題（選擇＋同考點申論）</div>${gs}</div>`;
  }
  const tot=sub.issues.reduce((a,i)=>a+i.total,0);
  const rank=s=>s==='高普考領先'?0:s==='法律系考古題'?1:s==='期刊論文'?2:3;
  const ut=[...(sub.untested||[])].sort((a,b)=>rank(a.source)-rank(b.source));
  const utRows=ut.map(u=>{
    const m=srcMeta(u.source);
    return `<div class="row ut"><span class="label" data-id="${esc(u.id)}">${esc(u.label)}</span>
      <span class="circs"><span class="circ pred ${m.c}">${m.b}</span></span></div>`;
  }).join('');
  const cnt=s=>ut.filter(u=>u.source===s).length;
  const utSec=ut.length?`<div class="gname pred">🔮 還沒考過的重要爭點（${ut.length}：🔮研究${cnt('研究推測')}＋📈高普考${cnt('高普考領先')}＋🎓法律系${cnt('法律系考古題')}＋📚期刊${cnt('期刊論文')}，字號已驗）—— 點看學說/實務/為何可能考</div>${utRows}`:'';
  return `<div class="card"><h3>${esc(sub.subject)}</h3>
    <div class="meta">${sub.issues.length} 個已考爭點 · ${tot} 題（申論）· 反覆考者粗體</div>${rows(sub.issues,true)}${utSec}</div>`;
}
function shortName(s){const m=s.match(/（(.+)）/);return m?m[1]:s;}
function subjectBar(tab){
  const chips=DATA[tab].map((s,i)=>`<button class="sbtn" data-tab="${tab}" data-i="${i}">${esc(shortName(s.subject))}</button>`).join('');
  return chips+`<button class="sbtn uc" data-tab="${tab}" data-i="uncov">🆕 未考過 ${DATA.uncovered_list.length}</button>`;
}
function renderUncov(){
  const u=DATA.uncovered_list||[];
  const body=u.length?`<div class="pills">${u.map(t=>`<span class="upill">${esc(t)}</span>`).join('')}</div>`
    :'<p style="color:#86868b;font-size:13px">（用內容關鍵字檢查，沒有確定未考的考點）</p>';
  return `<div class="card ucard"><h3>🆕 題庫關鍵字未命中（${u.length}）</h3>
    <div class="meta">用「內容關鍵字」判斷，不信分類標籤。注意：原本誤判的『未考』多是分類把題目貼到鄰近標籤（如<b>國家賠償 19 題被歸成行政訴訟</b>），其實有考。此處僅列 109–114 題庫關鍵字也搜不到者（可能換句話說或本區間未出）。</div>${body}</div>`;
}
function selectSubject(tab,i){
  document.querySelectorAll('.sbtn').forEach(b=>b.classList.toggle('on', b.dataset.tab===tab && String(b.dataset.i)===String(i)));
  $('#content').innerHTML = (i==='uncov') ? renderUncov() : subjectCard(tab, DATA[tab][i]);
  window.scrollTo(0,0);
}
function show(tab){
  $('#t1').classList.toggle('on',tab==='sl1'); $('#t2').classList.toggle('on',tab==='sl2');
  $('#subbar').innerHTML=subjectBar(tab);
  selectSubject(tab,0);
}
function openDrawer(id,year){
  const by=DATA.detail[id]||{}, label=id.slice(2);
  let qs, suffix;
  if(year){ qs=by[year]||[]; suffix=`・${year} 年（${qs.length} 題）`; }
  else { const ys=Object.keys(by).sort((a,b)=>b-a); qs=[].concat(...ys.map(y=>by[y])); suffix=`（${qs.length} 題）`; }
  $('#dtitle').textContent=label+suffix;
  const en=(id[0]==='e')?(DATA.enrich&&DATA.enrich[id]):null;  // tested 爭點 enrich 後學說/實務
  const qhtml=qs.map(q=>{
    let ex='';
    if(!en){  // enrich 存在時逐題籠統學說/實務不重複顯示（頂端統一顯示 enrich 版）
      if(q.doctrines&&q.doctrines.length) ex+=`<div class="tag doc-t">學說</div>`+q.doctrines.map(d=>`<div class="di">${beautify(esc(d))}</div>`).join('');
      if(q.practice&&q.practice.length) ex+=`<div class="tag prac-t">實務</div><div class="pr">${q.practice.map(d=>beautify(esc(d))).join('｜')}</div>`;
    }
    if(q.untested){
      const m=srcMeta(q.source);
      const extra=q.gk_source||q.ls_source||q.journal_source||'';
      const badge=m.b+(extra?'（'+esc(extra)+'）':'');
      const why=q.why?`<div class="tag">為何可能考</div><div class="di" style="background:#f3eeff">${esc(q.why)}</div>`:'';
      return `<div class="q"><span class="yr" style="background:${m.bg}">${badge}</span>
        <div class="stem" style="font-weight:600;margin-top:6px">${esc(q.issue||'')}</div>${ex}${why}</div>`;
    }
    const kind=q.essay?'申論':'選擇';
    const opts=q.options?optionsHtml(q.options,q.correct):'';  // 選擇題選項＋正解
    return `<div class="q"><span class="yr">${q.year} 年</span><span class="qid">${esc(q.qid)} · ${kind}</span>
      <div class="stem">${formatStem(q.stem,q.focus)}</div>${opts}${ex}</div>`;
  }).join('')||'<p style="color:#86868b">（無資料）</p>';
  // 擬答（單年抽屜，每題）→ 移到右欄「解析」
  const ansHtml=year?qs.filter(q=>q.answer).map(q=>`<div class="tag ans-t">擬答</div><div class="md ans">${q.answer}</div>`).join(''):'';
  // tested 爭點：enrich 後的學說(含學者)/實務(具體字號)
  let enh='';
  if(en){
    if(en.doctrines&&en.doctrines.length) enh+=`<div class="tag doc-t">學說（含學者／標準說）</div>`+en.doctrines.map(d=>`<div class="di">${beautify(esc(d))}</div>`).join('');
    if(en.practice&&en.practice.length) enh+=`<div class="tag prac-t">實務（字號·已驗）</div><div class="pr">${en.practice.map(d=>beautify(esc(d))).join('｜')}</div>`;
  }
  const analysis=ansHtml+enh;  // 需 .q 祖先讓 .tag/.di/.pr 樣式生效
  const prim=(DATA.primers&&DATA.primers[id])?`<div class="primer"><div class="ptag">◆ 考點重點 ◆</div><div class="md">${DATA.primers[id]}</div></div>`:'';
  const right=(analysis?`<div class="q">${analysis}</div>`:'')+prim;
  // 全螢幕配版：有解析 → 左欄題目／右欄解析(擬答+學說實務+考點重點)；無解析 → 單欄置中限寬好讀
  $('#dbody').innerHTML = right.trim()
    ? `<div class="cols"><div class="col-q">${qhtml}</div><div class="col-a">${right}</div></div>`
    : `<div class="solo">${qhtml}</div>`;
  $('#scrim').classList.add('on');$('#drawer').classList.add('on');
}
function closeDrawer(){$('#scrim').classList.remove('on');$('#drawer').classList.remove('on');}
document.addEventListener('click',e=>{
  const op=e.target.closest('.opt');  // 選擇題作答：先選才揭示正解
  if(op){const box=op.closest('.opts');
    if(box&&!box.classList.contains('answered')){
      const correct=box.dataset.correct; box.classList.add('answered');
      box.querySelectorAll('.opt').forEach(o=>{if(o.dataset.letter===correct){o.classList.add('ok');o.insertAdjacentHTML('beforeend','<span class="ck">✓ 正解</span>');}});
      if(op.dataset.letter!==correct){op.classList.add('wrong');op.insertAdjacentHTML('beforeend','<span class="ck wrongck">✗ 你選的</span>');}
    }
    return;}
  const b=e.target.closest('.sbtn'); if(b){selectSubject(b.dataset.tab, b.dataset.i==='uncov'?'uncov':+b.dataset.i);return;}
  const c=e.target.closest('.circ[data-id]'); if(c){openDrawer(c.dataset.id,c.dataset.year);return;}
  const l=e.target.closest('.label[data-id]'); if(l){openDrawer(l.dataset.id,null);}
});
window.addEventListener('DOMContentLoaded',()=>{
  show('sl1');
  $('#t1').onclick=()=>show('sl1'); $('#t2').onclick=()=>show('sl2');
  $('#scrim').onclick=closeDrawer; $('#dx').onclick=closeDrawer;
});
"""


def render(data: dict) -> str:
    s = data["summary"]
    blob = json.dumps(data, ensure_ascii=False)
    chips = "".join(
        '<span class="chip"><b>' + str(v) + "</b> " + lbl + "</span>"
        for v, lbl in [(s["mcq_topics"], "考點"), (s["essay_issues"], "申論爭點"),
                       (s.get("untested", 0), "推測未考"), (s["total_q"], "題")]
    )
    legend = (
        '<div class="legend"><span>圈內＝民國年 · 顏色越深＝年份越近 · '
        '×N＝該年題數 · 點圈看該年原題</span></div>'
    )
    return (
        '<!doctype html><html lang="zh-Hant"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1"><title>考點地圖</title>'
        "<style>" + _CSS + "</style></head><body>"
        '<div class="topbar"><h1>考點地圖 · 司律</h1>' + chips
        + '<div class="tabs"><button class="tab" id="t1">一試（選擇）</button>'
        '<button class="tab" id="t2">二試（申論）</button></div></div>'
        '<div id="subbar" class="subbar"></div>' + legend
        + '<div class="wrap"><div id="content"></div></div>'
        '<div class="scrim" id="scrim"></div>'
        '<aside class="drawer" id="drawer"><header><h2 id="dtitle"></h2>'
        '<button class="x" id="dx">×</button></header>'
        '<div class="body" id="dbody"></div></aside>'
        "<script>const DATA=" + blob + ";</script><script>" + _JS + "</script></body></html>"
    )


def main(argv=None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    out = Path(argv[0]) if argv else Path("topic-atlas.html")
    conn = db.connect(db.default_db_path())
    db.init_schema(conn)         # 確保 ephemeral 表 schema 存在（CREATE IF NOT EXISTS，冪等）
    db.apply_issue_canon(conn)   # 重建 ephemeral 爭點正規化表（bundled issue_canon.json）
    db.apply_essay_issues(conn)  # 重建 ephemeral 爭點索引（bundled essay_issues.json）
    data = assemble(conn)
    out.write_text(render(data), encoding="utf-8")
    s = data["summary"]
    print(f"[atlas] {s['mcq_topics']} 考點 | {s['essay_issues']} 申論爭點 | "
          f"{s['uncovered']} 關鍵字未命中 | {s['total_q']} 題")
    print(f"[atlas] wrote {out.resolve()} ({out.stat().st_size//1024} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
