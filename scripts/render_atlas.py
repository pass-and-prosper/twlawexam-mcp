#!/usr/bin/env python
"""Unified interactive 考點地圖 (一試選擇 + 二試申論) → self-contained HTML.

By 科目. 選擇題 shown at topic_point level (with 未考過 markers), 申論題 at
canonical 爭點 level (recurring 爭點 first). Click any 考點/爭點 → a drawer lists
the original past questions (year + stem, and 學說/實務 for essays).

Usage:  python scripts/render_atlas.py [out.html]   # default topic-atlas.html
"""
from __future__ import annotations
import html
import json
import sys
from pathlib import Path

from twexam_mcp.cache import db
from twexam_mcp.tools.exam_map import _SL1_MAP, _SL2_MAP, _all_syllabus_topics


def assemble(conn) -> dict:
    # 選擇題 questions grouped by topic_point
    mcq_by_topic: dict[str, list] = {}
    for qid, year, stem, tp in conn.execute(
        "SELECT qid, year, stem, topic_point FROM questions "
        "WHERE q_type='mcq' AND topic_point IS NOT NULL"
    ):
        mcq_by_topic.setdefault(tp, []).append({"qid": qid, "year": year, "stem": stem})

    # 申論 essays grouped by canonical 爭點
    ess_by_canon: dict[str, list] = {}
    canon_subject: dict[str, str] = {}
    for qid, year, stem, issue, canon, doc, prac, ts in conn.execute(
        """SELECT e.qid, q.year, q.stem, e.issue, COALESCE(c.canonical, e.issue),
                  e.doctrines, e.practice, e.topic_subject
           FROM essay_issues e JOIN questions q ON q.qid=e.qid
           LEFT JOIN issue_canon c ON c.issue=e.issue"""
    ):
        ess_by_canon.setdefault(canon, []).append(
            {"qid": qid, "year": year, "stem": stem,
             "doctrines": json.loads(doc), "practice": json.loads(prac), "issue": issue})
        canon_subject[canon] = ts

    detail: dict[str, list] = {}

    # 一試: syllabus 科目 → 子科目 → topic_point
    sl1 = []
    for it in _SL1_MAP:
        groups = []
        for ss in it["sub_subjects"]:
            topics = []
            for t in ss["topics"]:
                qs = sorted(mcq_by_topic.get(t, []), key=lambda x: -x["year"])
                idd = "m:" + t
                detail[idd] = qs
                topics.append({"id": idd, "label": t, "count": len(qs), "examined": bool(qs)})
            groups.append({"name": ss["name"], "topics": topics})
        sl1.append({"subject": it["subject"], "groups": groups})

    # 二試: 科目 → canonical 爭點 (recurring first)
    by_subject: dict[str, list] = {}
    for canon, qs in ess_by_canon.items():
        by_subject.setdefault(canon_subject[canon], []).append((canon, qs))
    # keep 科目 order as in _SL2_MAP, then any extras
    order = [it["subject"] for it in _SL2_MAP]
    subj_keys = sorted(by_subject, key=lambda s: (order.index(s) if s in order else 99, s))
    sl2 = []
    for ts in subj_keys:
        issues = []
        for canon, qs in by_subject[ts]:
            idd = "e:" + canon
            detail[idd] = sorted(qs, key=lambda x: -x["year"])
            n = len({q["qid"] for q in qs})
            issues.append({"id": idd, "label": canon, "count": n, "recurring": n >= 2})
        issues.sort(key=lambda x: (-x["count"], x["label"]))
        sl2.append({"subject": ts, "issues": issues})

    # 真正「未考過」= 該考點全題型(選擇+申論) 都 0 題
    tested = {r[0] for r in conn.execute(
        "SELECT DISTINCT topic_point FROM questions WHERE topic_point IS NOT NULL")}
    syll = _all_syllabus_topics()
    uncovered_list = sorted(t for t in syll if t not in tested)
    return {
        "sl1": sl1, "sl2": sl2, "detail": detail,
        "uncovered_list": uncovered_list,
        "summary": {
            "mcq_topics": len(syll),
            "essay_issues": sum(len(s["issues"]) for s in sl2),
            "uncovered": len(uncovered_list),
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
.wrap{max-width:1080px;margin:0 auto;padding:22px 20px 90px;}
.card{background:var(--card);border:1px solid var(--line);border-radius:18px;padding:16px 20px;margin-bottom:14px;box-shadow:0 1px 3px rgba(0,0,0,.04);}
.card h3{margin:0 0 2px;font-size:16px;font-weight:600;}
.card .meta{font-size:12px;color:var(--muted);margin-bottom:10px;}
.gname{font-size:12.5px;font-weight:600;color:#6e6e73;margin:12px 0 6px;}
.row{display:flex;align-items:center;gap:10px;padding:4px 0;cursor:pointer;}
.row:hover .label{color:var(--blue);}
.label{flex:0 0 auto;font-size:13.5px;min-width:0;}
.barwrap{flex:1;height:10px;background:#f0f0f4;border-radius:6px;overflow:hidden;}
.bar{height:100%;background:linear-gradient(90deg,#7fbef9,#0a5fc2);border-radius:6px;}
.cnt{flex:0 0 auto;font-size:12.5px;font-weight:700;color:#3a3a3c;width:30px;text-align:right;}
.row.recur .cnt{color:var(--blue);}
.row.uncov{cursor:default;opacity:.85;}
.row.uncov .pill{font-size:11px;font-weight:700;color:#fff;background:var(--orange);padding:1px 8px;border-radius:980px;}
.row.uncov .barwrap{background:repeating-linear-gradient(90deg,#fde8cf,#fde8cf 6px,transparent 6px,transparent 12px);}
.hidden{display:none;}
.scrim{position:fixed;inset:0;background:rgba(0,0,0,.25);opacity:0;pointer-events:none;transition:.2s;z-index:20;}
.scrim.on{opacity:1;pointer-events:auto;}
.drawer{position:fixed;top:0;right:0;height:100%;width:min(560px,92vw);background:var(--card);z-index:21;
 transform:translateX(100%);transition:transform .24s cubic-bezier(.4,0,.2,1);box-shadow:-8px 0 40px rgba(0,0,0,.18);
 display:flex;flex-direction:column;}
.drawer.on{transform:translateX(0);}
.drawer header{padding:18px 22px;border-bottom:1px solid var(--line);display:flex;gap:12px;align-items:flex-start;}
.drawer header h2{font-size:16px;margin:0;font-weight:600;line-height:1.4;flex:1;}
.drawer .x{border:none;background:#e8e8ed;border-radius:50%;width:30px;height:30px;font-size:16px;cursor:pointer;color:#3a3a3c;flex:0 0 auto;}
.drawer .body{overflow:auto;padding:8px 22px 30px;}
.q{padding:14px 0;border-bottom:1px solid var(--line);}
.q .yr{display:inline-block;font-size:12px;font-weight:700;color:#fff;background:var(--blue);padding:2px 9px;border-radius:980px;margin-right:8px;}
.q .qid{font-size:11.5px;color:var(--muted);}
.q .stem{margin:8px 0 0;font-size:13.5px;line-height:1.7;white-space:pre-wrap;}
.q .tag{font-size:11px;font-weight:600;color:#6e6e73;margin-top:8px;}
.q .di{font-size:12.5px;line-height:1.6;color:#1d1d1f;background:#f5f5f7;border-radius:8px;padding:6px 10px;margin-top:4px;}
.q .pr{font-size:12px;color:#0a5fc2;margin-top:4px;}
.ucard{border:1px solid #ffe0b8;background:#fffaf3;}
.pills{display:flex;flex-wrap:wrap;gap:7px;}
.upill{font-size:13px;padding:5px 11px;border-radius:980px;background:#fff;border:1.5px dashed var(--orange);color:#9a5b00;font-weight:500;}
"""

_JS = """
const $=s=>document.querySelector(s);
function bars(items, max){
  return items.map(it=>{
    if(it.examined===false){
      return `<div class="row uncov"><span class="label">${esc(it.label)}</span>
        <div class="barwrap"></div><span class="pill">未考</span></div>`;
    }
    const w=Math.max(4, Math.round(it.count/max*100));
    const rec=it.recurring?' recur':'';
    return `<div class="row${rec}" data-id="${esc(it.id)}"><span class="label">${esc(it.label)}</span>
      <div class="barwrap"><div class="bar" style="width:${w}%"></div></div><span class="cnt">${it.count}</span></div>`;
  }).join('');
}
function esc(s){return (s+'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));}
function renderSL1(){
  return DATA.sl1.map(sub=>{
    const tot=sub.groups.reduce((a,g)=>a+g.topics.reduce((b,t)=>b+t.count,0),0);
    const groups=sub.groups.map(g=>{
      const max=Math.max(1,...g.topics.map(t=>t.count));
      const sorted=[...g.topics].sort((a,b)=>b.count-a.count);
      return `<div class="gname">${esc(g.name)}</div>${bars(sorted,max)}`;
    }).join('');
    return `<div class="card"><h3>${esc(sub.subject)}</h3><div class="meta">合計 ${tot} 題（選擇）</div>${groups}</div>`;
  }).join('');
}
function renderSL2(){
  return DATA.sl2.map(sub=>{
    const tot=sub.issues.reduce((a,i)=>a+i.count,0);
    const max=Math.max(1,...sub.issues.map(i=>i.count));
    return `<div class="card"><h3>${esc(sub.subject)}</h3><div class="meta">${sub.issues.length} 個爭點 · ${tot} 題（申論）</div>${bars(sub.issues,max)}</div>`;
  }).join('');
}
function show(tab){
  $('#sl1').classList.toggle('hidden',tab!=='sl1');
  $('#sl2').classList.toggle('hidden',tab!=='sl2');
  $('#t1').classList.toggle('on',tab==='sl1');
  $('#t2').classList.toggle('on',tab==='sl2');
}
function openDrawer(id){
  const qs=DATA.detail[id]||[];
  const label=id.slice(2);
  $('#dtitle').textContent=label+`（${new Set(qs.map(q=>q.qid)).size} 題）`;
  $('#dbody').innerHTML=qs.map(q=>{
    let extra='';
    if(q.doctrines&&q.doctrines.length) extra+=`<div class="tag">學說</div>`+q.doctrines.map(d=>`<div class="di">${esc(d)}</div>`).join('');
    if(q.practice&&q.practice.length) extra+=`<div class="tag">實務</div><div class="pr">${q.practice.map(esc).join('｜')}</div>`;
    return `<div class="q"><span class="yr">${q.year} 年</span><span class="qid">${esc(q.qid)}</span>
      <div class="stem">${esc(q.stem)}</div>${extra}</div>`;
  }).join('')||'<p style="color:#86868b">（無資料）</p>';
  $('#scrim').classList.add('on');$('#drawer').classList.add('on');
}
function closeDrawer(){$('#scrim').classList.remove('on');$('#drawer').classList.remove('on');}
document.addEventListener('click',e=>{
  const row=e.target.closest('.row[data-id]'); if(row) openDrawer(row.dataset.id);
});
function renderUncov(){
  const u=DATA.uncovered_list||[];
  if(!u.length) return '';
  const pills=u.map(t=>`<span class="upill">${esc(t)}</span>`).join('');
  return `<div class="card ucard"><h3>🆕 還沒考過的考點（${u.length}）</h3>
    <div class="meta">母清單有、歷屆零題（選擇＋申論都沒考過）</div><div class="pills">${pills}</div></div>`;
}
window.addEventListener('DOMContentLoaded',()=>{
  $('#uncov').innerHTML=renderUncov();
  $('#sl1').innerHTML=renderSL1(); $('#sl2').innerHTML=renderSL2(); show('sl1');
  $('#t1').onclick=()=>show('sl1'); $('#t2').onclick=()=>show('sl2');
  $('#scrim').onclick=closeDrawer; $('#dx').onclick=closeDrawer;
});
"""


def render(data: dict) -> str:
    s = data["summary"]
    blob = json.dumps(data, ensure_ascii=False)
    chips = "".join(
        '<span class="chip"><b>' + str(v) + "</b> " + lbl + "</span>"
        for v, lbl in [(s["mcq_topics"], "選擇考點"), (s["essay_issues"], "申論爭點"),
                       (s["uncovered"], "未考過"), (s["total_q"], "題")]
    )
    return (
        '<!doctype html><html lang="zh-Hant"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1"><title>考點地圖</title>'
        "<style>" + _CSS + "</style></head><body>"
        '<div class="topbar"><h1>考點地圖 · 司律</h1>' + chips
        + '<div class="tabs"><button class="tab" id="t1">一試（選擇）</button>'
        '<button class="tab" id="t2">二試（申論）</button></div></div>'
        '<div class="wrap"><div id="uncov"></div><div id="sl1"></div><div id="sl2"></div></div>'
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
    print(f"[atlas] {s['mcq_topics']} 選擇考點 | {s['essay_issues']} 申論爭點 | "
          f"{s['uncovered']} 未考 | {s['total_q']} 題")
    print(f"[atlas] wrote {out.resolve()} ({out.stat().st_size//1024} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
