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
import json
import sys
from pathlib import Path

from twexam_mcp.cache import db
from twexam_mcp.tools.exam_map import _SL1_MAP, _SL2_MAP, _all_syllabus_topics


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
        ess_canon.setdefault(canon, {}).setdefault(year, []).append(
            {"qid": qid, "year": year, "stem": stem, "essay": True,
             "doctrines": json.loads(doc), "practice": json.loads(prac), "issue": issue})
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

    def entry_canon(idd, label, by_year):
        detail[idd] = {str(y): by_year[y] for y in by_year}
        years = [{"year": y, "count": len(by_year[y]), "essay": True} for y in sorted(by_year)]
        total = sum(len(v) for v in by_year.values())
        return {"id": idd, "label": label, "years": years, "total": total,
                "examined": total > 0, "recurring": total >= 2}

    by_subject: dict[str, list] = {}
    for canon, by_year in ess_canon.items():
        by_subject.setdefault(canon_subject[canon], []).append((canon, by_year))
    order = [it["subject"] for it in _SL2_MAP]
    subj_keys = sorted(by_subject, key=lambda s: (order.index(s) if s in order else 99, s))
    sl2 = []
    for ts in subj_keys:
        issues = [entry_canon("e:" + canon, canon, by_year) for canon, by_year in by_subject[ts]]
        issues.sort(key=lambda x: (-x["total"], x["label"]))
        sl2.append({"subject": ts, "issues": issues})

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

    uncovered_list = [t for t in sorted(_all_syllabus_topics())
                      if t not in tested and not any(_seen(k) for k in syn.get(t, [t]))]

    return {
        "sl1": sl1, "sl2": sl2, "detail": detail, "uncovered_list": uncovered_list,
        "summary": {
            "mcq_topics": len(_all_syllabus_topics()),
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
 background:#5a5a5e;border-radius:980px;padding:0 5px;line-height:15px;}
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
const BLUE={109:'#dcecfb',110:'#bcdcfa',111:'#94c6f6',112:'#5aa6f0',113:'#2f8be8',114:'#0a5fc2'};
function esc(s){return (s+'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));}
function circles(e){
  if(!e.examined) return '<span class="circ none">未考</span>';
  return e.years.map(y=>{
    const fill=BLUE[y.year]||'#7fbef9';
    const badge=y.count>1?`<i>×${y.count}</i>`:'';
    return `<span class="circ" data-id="${esc(e.id)}" data-year="${y.year}" title="${y.year}年 ${y.count}題"
      style="background:${fill};color:${y.year>=112?'#fff':'#06294d'}">${y.year}${badge}</span>`;
  }).join('');
}
function rows(items,recur){
  const sorted=[...items].sort((a,b)=>b.total-a.total);
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
  return `<div class="card"><h3>${esc(sub.subject)}</h3>
    <div class="meta">${sub.issues.length} 個爭點 · ${tot} 題（申論）· 反覆考者粗體</div>${rows(sub.issues,true)}</div>`;
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
  $('#dbody').innerHTML=qs.map(q=>{
    const kind=q.essay?'申論':'選擇';
    let ex='';
    if(q.doctrines&&q.doctrines.length) ex+=`<div class="tag">學說</div>`+q.doctrines.map(d=>`<div class="di">${esc(d)}</div>`).join('');
    if(q.practice&&q.practice.length) ex+=`<div class="tag">實務</div><div class="pr">${q.practice.map(esc).join('｜')}</div>`;
    return `<div class="q"><span class="yr">${q.year} 年</span><span class="qid">${esc(q.qid)} · ${kind}</span>
      <div class="stem">${esc(q.stem)}</div>${ex}</div>`;
  }).join('')||'<p style="color:#86868b">（無資料）</p>';
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
                       (s["uncovered"], "未命中"), (s["total_q"], "題")]
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
