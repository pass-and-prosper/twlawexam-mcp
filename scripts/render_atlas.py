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
    for qid, year, stem, tp, qtype in conn.execute(
        "SELECT qid, year, stem, topic_point, q_type FROM questions WHERE topic_point IS NOT NULL"
    ):
        bucket = es_t if qtype == "essay" else mcq
        bucket.setdefault(tp, {}).setdefault(year, []).append(
            {"qid": qid, "year": year, "stem": stem, "essay": qtype == "essay"})

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

    def entry_canon(idd, label, by_year, answers=None):
        answers = answers or {}
        rows = {str(y): list(by_year[y].values()) for y in by_year}  # by_year[y] is {qid:entry}
        for qs in rows.values():
            for q in qs:
                if q["qid"] in answers:  # 各題擬答（單年抽屜才顯示，由 JS 控制）
                    q["answer"] = _md_to_html(answers[q["qid"]])
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
    primers: dict[str, str] = {}  # id('e:'+canon) -> 渲染後的重點 HTML

    sl2 = []
    n_untested = 0
    for ts in subj_keys:
        issues = []
        for canon, by_year in by_subject[ts]:
            pid = "e:" + canon
            pdata = primers_src.get(canon, {})
            issues.append(entry_canon(pid, canon, by_year, pdata.get("answers")))
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
.drawer{position:fixed;top:0;right:0;height:100%;width:min(680px,95vw);background:var(--card);z-index:21;
 transform:translateX(100%);transition:transform .24s cubic-bezier(.4,0,.2,1);box-shadow:-8px 0 40px rgba(0,0,0,.18);display:flex;flex-direction:column;}
.drawer.on{transform:translateX(0);}
.drawer header{padding:20px 28px;border-bottom:1px solid var(--line);display:flex;gap:12px;align-items:flex-start;}
.drawer header h2{font-size:18px;margin:0;font-weight:600;line-height:1.45;flex:1;}
.drawer .x{border:none;background:#e8e8ed;border-radius:50%;width:32px;height:32px;font-size:17px;cursor:pointer;color:#3a3a3c;flex:0 0 auto;}
.drawer .body{overflow:auto;padding:14px 28px 46px;}
.q{padding:18px 0;border-bottom:1px solid var(--line);}
.q .yr{display:inline-block;font-size:13px;font-weight:700;color:#fff;background:var(--blue);padding:3px 11px;border-radius:980px;margin-right:9px;}
.q .qid{font-size:12.5px;color:var(--muted);}
.q .stem{margin:11px 0 0;font-size:15.5px;line-height:1.9;white-space:pre-wrap;}
.q .tag{font-size:12.5px;font-weight:800;color:#6e6e73;margin-top:14px;letter-spacing:.02em;}
.q .tag.doc-t{color:#0a6cff;}      /* 學說＝藍 */
.q .tag.prac-t{color:#1b9e57;}     /* 實務＝綠 */
.q .di{font-size:14.5px;line-height:1.85;background:#eef4ff;border-left:3px solid #0a6cff;border-radius:0 10px 10px 0;padding:10px 14px;margin:6px 0;}
.q .pr{font-size:14px;line-height:1.8;background:#e9f8f0;border-left:3px solid #1b9e57;border-radius:0 10px 10px 0;padding:10px 14px;margin:6px 0;color:#0c6b3c;}
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
/* 擬答（單年抽屜）＋ 考點重點(primer) */
.q .tag.ans-t{color:#0a5fc2;}
.ans{font-size:15px;line-height:1.9;background:#eef6ff;border:1px solid #d4e6fb;border-left:3px solid var(--blue);
 border-radius:10px;padding:12px 16px;margin-top:6px;}
.primer{margin-top:26px;background:#f5f5f7;border:1px solid var(--line);border-radius:16px;padding:18px 22px;}
.primer .ptag{font-size:14px;font-weight:700;color:#3a3a3c;letter-spacing:.05em;margin-bottom:12px;text-align:center;}
.md{font-size:14.5px;line-height:1.9;color:var(--ink);}
.md h4{font-size:15.5px;font-weight:700;margin:16px 0 8px;}
.md h4:first-child{margin-top:0;}
.md p{margin:9px 0;}
.md ol,.md ul{margin:8px 0;padding-left:24px;}
.md li{margin:7px 0;line-height:1.85;}
.md ul{list-style:disc;}
.md code{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;font-size:13.5px;
 background:#e8eef5;color:#0a4a8c;padding:1px 6px;border-radius:5px;}
.md strong{font-weight:700;}
.md hr{border:none;border-top:1px solid var(--line);margin:14px 0;}
"""

_JS = """
const $=s=>document.querySelector(s);
const BLUE={109:'#dcecfb',110:'#bcdcfa',111:'#94c6f6',112:'#5aa6f0',113:'#2f8be8',114:'#0a5fc2'};
function esc(s){return (s+'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));}
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
      if(q.doctrines&&q.doctrines.length) ex+=`<div class="tag">學說</div>`+q.doctrines.map(d=>`<div class="di">${esc(d)}</div>`).join('');
      if(q.practice&&q.practice.length) ex+=`<div class="tag">實務</div><div class="pr">${q.practice.map(esc).join('｜')}</div>`;
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
    // 擬答：只在「點進單年」那一題顯示（year 有值＝單年抽屜）；內容為已渲染 HTML
    const ans=(year&&q.answer)?`<div class="tag ans-t">擬答</div><div class="md ans">${q.answer}</div>`:'';
    return `<div class="q"><span class="yr">${q.year} 年</span><span class="qid">${esc(q.qid)} · ${kind}</span>
      <div class="stem">${esc(q.stem)}</div>${ans}${ex}</div>`;
  }).join('')||'<p style="color:#86868b">（無資料）</p>';
  // tested 爭點：enrich 後的學說(含學者)/實務(具體字號)，放在題目下方統一顯示一次
  let enh='';
  if(en){
    if(en.doctrines&&en.doctrines.length) enh+=`<div class="tag">學說（含學者／標準說）</div>`+en.doctrines.map(d=>`<div class="di">${esc(d)}</div>`).join('');
    if(en.practice&&en.practice.length) enh+=`<div class="tag">實務（字號·已驗）</div><div class="pr">${en.practice.map(esc).join('｜')}</div>`;
    if(enh) enh=`<div class="q" style="border-bottom:2px solid var(--line)">${enh}</div>`;
  }
  // 考點重點(primer)：放在最下方，全年份/單年都顯示
  const prim=(DATA.primers&&DATA.primers[id])?`<div class="primer"><div class="ptag">◆ 考點重點 ◆</div><div class="md">${DATA.primers[id]}</div></div>`:'';
  // 題目最上方 → 學說/實務(enrich) → 考點重點
  $('#dbody').innerHTML=qhtml+enh+prim;
  $('#scrim').classList.add('on');$('#drawer').classList.add('on');
}
function closeDrawer(){$('#scrim').classList.remove('on');$('#drawer').classList.remove('on');}
document.addEventListener('click',e=>{
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
    data = assemble(conn)
    out.write_text(render(data), encoding="utf-8")
    s = data["summary"]
    print(f"[atlas] {s['mcq_topics']} 考點 | {s['essay_issues']} 申論爭點 | "
          f"{s['uncovered']} 關鍵字未命中 | {s['total_q']} 題")
    print(f"[atlas] wrote {out.resolve()} ({out.stat().st_size//1024} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
