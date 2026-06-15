#!/usr/bin/env python
"""Unified interactive 考點地圖 (一試選擇 + 二試申論) → self-contained HTML.

By 科目. Each 考點 / 爭點 shows a row of YEAR CIRCLES — one circle per 民國 year
it was tested, the year printed inside, ×N if several that year, recent years
darker. Click a year-circle → a drawer lists that year's original questions
(stem, and 學說/實務 for essays). 未考過 考點 are flagged.

Usage:  python scripts/render_atlas.py [out.html]   # default topic-atlas.html
"""
from __future__ import annotations
import json
import sys
from pathlib import Path

from twexam_mcp.cache import db
from twexam_mcp.tools.exam_map import _SL1_MAP, _SL2_MAP, _all_syllabus_topics


def assemble(conn) -> dict:
    mcq: dict[str, dict] = {}      # topic_point -> {year: [q]}
    for qid, year, stem, tp in conn.execute(
        "SELECT qid, year, stem, topic_point FROM questions "
        "WHERE q_type='mcq' AND topic_point IS NOT NULL"
    ):
        mcq.setdefault(tp, {}).setdefault(year, []).append({"qid": qid, "year": year, "stem": stem})

    ess: dict[str, dict] = {}      # canonical 爭點 -> {year: [q]}
    canon_subject: dict[str, str] = {}
    for qid, year, stem, issue, canon, doc, prac, ts in conn.execute(
        """SELECT e.qid, q.year, q.stem, e.issue, COALESCE(c.canonical, e.issue),
                  e.doctrines, e.practice, e.topic_subject
           FROM essay_issues e JOIN questions q ON q.qid=e.qid
           LEFT JOIN issue_canon c ON c.issue=e.issue"""
    ):
        ess.setdefault(canon, {}).setdefault(year, []).append(
            {"qid": qid, "year": year, "stem": stem,
             "doctrines": json.loads(doc), "practice": json.loads(prac), "issue": issue})
        canon_subject[canon] = ts

    detail: dict[str, dict] = {}

    def entry(idd: str, label: str, by_year: dict) -> dict:
        detail[idd] = {str(y): by_year[y] for y in by_year}
        years = [{"year": y, "count": len(by_year[y])} for y in sorted(by_year)]
        total = sum(len(v) for v in by_year.values())
        return {"id": idd, "label": label, "years": years, "total": total, "examined": total > 0}

    sl1 = []
    for it in _SL1_MAP:
        groups = [{"name": ss["name"], "topics": [entry("m:" + t, t, mcq.get(t, {})) for t in ss["topics"]]}
                  for ss in it["sub_subjects"]]
        sl1.append({"subject": it["subject"], "groups": groups})

    by_subject: dict[str, list] = {}
    for canon, by_year in ess.items():
        by_subject.setdefault(canon_subject[canon], []).append((canon, by_year))
    order = [it["subject"] for it in _SL2_MAP]
    subj_keys = sorted(by_subject, key=lambda s: (order.index(s) if s in order else 99, s))
    sl2 = []
    for ts in subj_keys:
        issues = []
        for canon, by_year in by_subject[ts]:
            e = entry("e:" + canon, canon, by_year)
            e["recurring"] = e["total"] >= 2
            issues.append(e)
        issues.sort(key=lambda x: (-x["total"], x["label"]))
        sl2.append({"subject": ts, "issues": issues})

    tested = {r[0] for r in conn.execute(
        "SELECT DISTINCT topic_point FROM questions WHERE topic_point IS NOT NULL")}
    syll = _all_syllabus_topics()
    uncovered_list = sorted(t for t in syll if t not in tested)
    return {
        "sl1": sl1, "sl2": sl2, "detail": detail, "uncovered_list": uncovered_list,
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
.gname{font-size:12.5px;font-weight:600;color:#6e6e73;margin:14px 0 8px;}
.row{display:flex;align-items:center;gap:12px;padding:6px 0;border-bottom:1px solid #f3f3f6;}
.label{flex:0 0 240px;font-size:13.5px;cursor:pointer;line-height:1.4;}
.row:hover .label{color:var(--blue);}
.row.recur .label{font-weight:600;}
.circs{display:flex;flex-wrap:wrap;gap:7px;align-items:center;}
.circ{position:relative;width:40px;height:40px;border-radius:50%;display:flex;align-items:center;justify-content:center;
 font-size:13px;font-weight:700;cursor:pointer;transition:transform .08s;box-shadow:0 1px 2px rgba(0,0,0,.12);}
.circ:hover{transform:scale(1.08);}
.circ i{position:absolute;top:-4px;right:-6px;font-style:normal;font-size:10px;font-weight:700;color:#fff;
 background:var(--orange);border-radius:980px;padding:0 5px;line-height:15px;}
.circ.none{width:auto;height:auto;border-radius:980px;padding:5px 12px;background:#fff;border:1.5px dashed var(--orange);
 color:#9a5b00;font-size:12px;cursor:default;box-shadow:none;}
.hidden{display:none;}
.scrim{position:fixed;inset:0;background:rgba(0,0,0,.25);opacity:0;pointer-events:none;transition:.2s;z-index:20;}
.scrim.on{opacity:1;pointer-events:auto;}
.drawer{position:fixed;top:0;right:0;height:100%;width:min(560px,92vw);background:var(--card);z-index:21;
 transform:translateX(100%);transition:transform .24s cubic-bezier(.4,0,.2,1);box-shadow:-8px 0 40px rgba(0,0,0,.18);display:flex;flex-direction:column;}
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
.q .di{font-size:12.5px;line-height:1.6;background:#f5f5f7;border-radius:8px;padding:6px 10px;margin-top:4px;}
.q .pr{font-size:12px;color:#0a5fc2;margin-top:4px;}
.ucard{border:1px solid #ffe0b8;background:#fffaf3;}
.pills{display:flex;flex-wrap:wrap;gap:7px;}
.upill{font-size:13px;padding:5px 11px;border-radius:980px;background:#fff;border:1.5px dashed var(--orange);color:#9a5b00;font-weight:500;}
"""

_JS = """
const $=s=>document.querySelector(s);
const YRC={109:'#dcecfb',110:'#bcdcfa',111:'#94c6f6',112:'#5aa6f0',113:'#2f8be8',114:'#0a5fc2'};
function esc(s){return (s+'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));}
function circles(e){
  if(!e.examined) return '<span class="circ none">未考</span>';
  return e.years.map(y=>{
    const fill=YRC[y.year]||'#7fbef9', dark=y.year>=112;
    const badge=y.count>1?`<i>×${y.count}</i>`:'';
    return `<span class="circ" data-id="${esc(e.id)}" data-year="${y.year}" title="${y.year}年 ${y.count}題"
      style="background:${fill};color:${dark?'#fff':'#06294d'}">${y.year}${badge}</span>`;
  }).join('');
}
function rows(items,recur){
  const sorted=[...items].sort((a,b)=>b.total-a.total);
  return sorted.map(t=>`<div class="row${recur&&t.recurring?' recur':''}">
    <span class="label" data-id="${esc(t.id)}">${esc(t.label)}</span>
    <span class="circs">${circles(t)}</span></div>`).join('');
}
function renderSL1(){
  return DATA.sl1.map(sub=>{
    const tot=sub.groups.reduce((a,g)=>a+g.topics.reduce((b,t)=>b+t.total,0),0);
    const gs=sub.groups.map(g=>`<div class="gname">${esc(g.name)}</div>${rows(g.topics,false)}`).join('');
    return `<div class="card"><h3>${esc(sub.subject)}</h3><div class="meta">合計 ${tot} 題（選擇）</div>${gs}</div>`;
  }).join('');
}
function renderSL2(){
  return DATA.sl2.map(sub=>{
    const tot=sub.issues.reduce((a,i)=>a+i.total,0);
    return `<div class="card"><h3>${esc(sub.subject)}</h3>
      <div class="meta">${sub.issues.length} 個爭點 · ${tot} 題（申論）· 反覆考者粗體</div>${rows(sub.issues,true)}</div>`;
  }).join('');
}
function renderUncov(){
  const u=DATA.uncovered_list||[]; if(!u.length) return '';
  return `<div class="card ucard"><h3>🆕 還沒考過的考點（${u.length}）</h3>
    <div class="meta">母清單有、歷屆零題（選擇＋申論都沒考過）</div>
    <div class="pills">${u.map(t=>`<span class="upill">${esc(t)}</span>`).join('')}</div></div>`;
}
function show(tab){
  $('#sl1').classList.toggle('hidden',tab!=='sl1');
  $('#sl2').classList.toggle('hidden',tab!=='sl2');
  $('#t1').classList.toggle('on',tab==='sl1');
  $('#t2').classList.toggle('on',tab==='sl2');
}
function openDrawer(id,year){
  const by=DATA.detail[id]||{}, label=id.slice(2);
  let qs, suffix;
  if(year){ qs=by[year]||[]; suffix=`・${year} 年（${qs.length} 題）`; }
  else { const ys=Object.keys(by).sort((a,b)=>b-a); qs=[].concat(...ys.map(y=>by[y]));
         suffix=`（${qs.length} 題）`; }
  $('#dtitle').textContent=label+suffix;
  $('#dbody').innerHTML=qs.map(q=>{
    let ex='';
    if(q.doctrines&&q.doctrines.length) ex+=`<div class="tag">學說</div>`+q.doctrines.map(d=>`<div class="di">${esc(d)}</div>`).join('');
    if(q.practice&&q.practice.length) ex+=`<div class="tag">實務</div><div class="pr">${q.practice.map(esc).join('｜')}</div>`;
    return `<div class="q"><span class="yr">${q.year} 年</span><span class="qid">${esc(q.qid)}</span>
      <div class="stem">${esc(q.stem)}</div>${ex}</div>`;
  }).join('')||'<p style="color:#86868b">（無資料）</p>';
  $('#scrim').classList.add('on');$('#drawer').classList.add('on');
}
function closeDrawer(){$('#scrim').classList.remove('on');$('#drawer').classList.remove('on');}
document.addEventListener('click',e=>{
  const c=e.target.closest('.circ[data-id]'); if(c){openDrawer(c.dataset.id,c.dataset.year);return;}
  const l=e.target.closest('.label[data-id]'); if(l){openDrawer(l.dataset.id,null);}
});
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
